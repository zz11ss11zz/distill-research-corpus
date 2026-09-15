"""Synthetic regressions for preserving evidence and disposition history."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import distill_complete_knowledge_base as kb

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples/sofc"
kb.DEFAULT_CONFIG_PATH = EXAMPLE_ROOT / "config/research-corpus.json"
kb.configure_profile(EXAMPLE_ROOT, kb.DEFAULT_CONFIG_PATH)

class RefreshPreservationTests(unittest.TestCase):
    def setUp(self):
        kb.configure_profile(EXAMPLE_ROOT, kb.DEFAULT_CONFIG_PATH)
        self.temp = tempfile.TemporaryDirectory(prefix="kb_refresh_regression_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Fixtures carry their own profile and evidence reference, like a real project.
        profile = json.loads(kb.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        profile_path = self.root / "config/research-corpus.json"
        profile_path.parent.mkdir()
        profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        evidence = self.root / profile["evidence_rules"]["reference"]
        evidence.parent.mkdir(parents=True, exist_ok=True)
        original_evidence = kb.DEFAULT_CONFIG_PATH.parents[1] / profile["evidence_rules"]["reference"]
        evidence.write_bytes(original_evidence.read_bytes())
        self.output = self.root / "kb"
        self.output.mkdir()
        self.text = "La0.6Sr0.4Co0.2Fe0.8O3 cathode showed a polarization resistance of\n0.10 Ω cm2 at 650 °C in air."
        self.source_path = self.root / "source.txt"
        self.source_path.write_text(self.text, encoding="utf-8")
        self.inventory = [{"path": "source.txt", "extension": ".txt", "category": "paper", "sha256": kb.sha256_file(self.source_path), "size_bytes": self.source_path.stat().st_size, "read_error": None}]
        self.source = kb.canonicalize_inventory(self.inventory)[0][0]
        self.doc, generated = kb.extract_text_document(self.source_path, self.source)
        self.machine = copy.deepcopy(generated[0])
        self.machine["fact_id"] = "legacy_fragment_id"
        self.machine["evidence_text"] = "La0.6Sr0.4Co0.2Fe0.8O3 cathode showed a polarization resistance of"
        self.verified = {"fact_id": "verified_original_id", "source_id": self.source["source_id"], "page": 1,
                         "evidence_text": "Previously verified summary; machine regeneration must not overwrite it.", "verification_status": "human_verified",
                         "measurement_ids": ["old:measurement"], "review_note": "retain exactly", "value": 0.1}
        self.previous = [self.machine, self.verified]
        self.write("documents.json", [self.doc])
        self.write("evidence_facts.json", self.previous)
        self.write("datasets.json", [])
        self.write("manifest.json", {"quality_model": {"fact_extraction_version": kb.FACT_EXTRACTION_VERSION}})
        self.dispositions = {"review_note": "historical decision bundle", "dispositions": [
            {"fact_id": f["fact_id"], "source_id": f["source_id"], "page": 1, "verification_status": f["verification_status"],
             "formal_disposition": "reviewed_strict_candidate_rejected" if i == 0 else "human_verified_evidence_fact", "reason": "old reason",
             "decision_links": [{"decision_id": "old_decision", "measurement_ids": ["old:measurement"]}]} for i, f in enumerate(self.previous)]}
        self.write("evidence_fact_dispositions_2020-01-01.json", self.dispositions)

    def write(self, name, payload):
        (self.output / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def run_main(self, *flags):
        with patch.object(sys, "argv", ["distill", "--root", str(self.root), "--config", str(self.root / "config/research-corpus.json"), "--output", "kb", *flags]), \
                patch.object(kb, "inventory_files", return_value=self.inventory), contextlib.redirect_stdout(io.StringIO()) as out:
            kb.main()
        return json.loads(out.getvalue())

    def test_refresh_full_and_version_change_keep_verified_ids_payload_and_decisions(self):
        for flag in ("--refresh-facts", "--full", "version-change"):
            with self.subTest(mode=flag):
                self.write("evidence_facts.json", self.previous)
                self.write("evidence_fact_dispositions.json", self.dispositions)
                self.write("manifest.json", {"quality_model": {"fact_extraction_version": "old" if flag == "version-change" else kb.FACT_EXTRACTION_VERSION}})
                before_snapshot = (self.output / "evidence_fact_dispositions_2020-01-01.json").read_bytes()
                result = self.run_main(*([] if flag == "version-change" else [flag]))
                after = {f["fact_id"]: f for f in self.read("evidence_facts.json")}
                self.assertEqual(after[self.verified["fact_id"]], self.verified)
                self.assertEqual(after[self.machine["fact_id"]], self.machine)
                self.assertEqual(result["preserved_verified_facts"], 1)
                rows = {r["fact_id"]: r for r in self.read("evidence_fact_dispositions.json")["dispositions"]}
                self.assertEqual(rows[self.machine["fact_id"]], self.dispositions["dispositions"][0])
                self.assertEqual(set(rows), set(after))
                self.assertEqual(before_snapshot, (self.output / "evidence_fact_dispositions_2020-01-01.json").read_bytes())
                self.assertTrue(all(f["verification_status"] == kb.MACHINE_FACT_STATUS for fid, f in after.items() if fid not in {p["fact_id"] for p in self.previous}))

    def test_corrupt_fact_file_fails_closed_even_on_full(self):
        (self.output / "evidence_facts.json").write_text("broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.run_main("--full")
        self.assertEqual((self.output / "evidence_facts.json").read_text(), "broken")

    def test_extraction_failure_leaves_original_files_intact_and_cleans_temps(self):
        old = {name: (self.output / name).read_bytes() for name in ("documents.json", "evidence_facts.json")}
        with patch.object(kb, "extract_text_document", side_effect=RuntimeError("fixture extraction failed")), self.assertRaises(RuntimeError):
            self.run_main("--full")
        for name, contents in old.items():
            self.assertEqual((self.output / name).read_bytes(), contents)
        self.assertEqual(list(self.output.glob("kb_refresh_*.tmp")), [])

    def test_absent_preserved_source_blocks_full(self):
        self.inventory = []
        old = (self.output / "evidence_facts.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "absent from inventory"):
            self.run_main("--full")
        self.assertEqual((self.output / "evidence_facts.json").read_bytes(), old)

    def test_overlay_restore_conflict_and_no_candidate_upgrade(self):
        overlay = self.root / "verified_overlay.json"
        restored = {**self.verified, "fact_id": "restored_id"}
        overlay.write_text(json.dumps({"facts": [restored]}), encoding="utf-8")
        result = kb.load_preserved_facts(self.output / "evidence_facts.json", [overlay])
        self.assertIn(restored, result)
        overlay.write_text(json.dumps([{**self.verified, "value": 99}]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            kb.load_preserved_facts(self.output / "evidence_facts.json", [overlay])
        overlay.write_text(json.dumps([self.machine]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unverified candidate"):
            kb.load_preserved_facts(self.output / "evidence_facts.json", [overlay])

    def test_softline_reflow_retains_temperature_without_crossing_paragraphs(self):
        one = kb.fact_candidates([{"page": 1, "text": self.text}], "fixture")
        flat = kb.fact_candidates([{"page": 1, "text": self.text.replace("\n", " ")}], "fixture")
        self.assertEqual(one[0]["evidence_text"], flat[0]["evidence_text"])
        self.assertEqual(one[0]["fact_id"], flat[0]["fact_id"])
        self.assertIn("650 °C", one[0]["temperature_candidates"])
        self.assertEqual(one[0]["verification_status"], kb.MACHINE_FACT_STATUS)
        text = self.text.replace("of\n", "of\n\n")
        hard = kb.fact_candidates([{"page": 1, "text": text}], "fixture")
        self.assertFalse(any("resistance" in f["evidence_text"] and "650" in f["evidence_text"] for f in hard))

    def test_identical_sentences_on_different_pages_keep_distinct_ids(self):
        facts = kb.fact_candidates([{"page": p, "text": self.text} for p in (1, 2)], "fixture")
        self.assertEqual(len(facts), 2)
        self.assertNotEqual(facts[0]["fact_id"], facts[1]["fact_id"])

    def test_span_offsets_hash_and_whitespace_id_preservation(self):
        text = "😀\n" + self.text
        fact = kb.fact_candidates([{"page": 1, "text": text}], "fixture")[0]
        span = fact["source_span"]
        raw = text.encode("utf-16-le")[span["start"] * 2:span["end"] * 2].decode("utf-16-le")
        self.assertEqual(kb.hashlib.sha256(raw.encode()).hexdigest(), span["raw_text_sha256"])
        old = {**fact, "fact_id": "keep_id", "evidence_text": fact["evidence_text"].replace("of ", "of\n")}
        merged, counts = kb.merge_preserved_facts([fact], [old])
        self.assertEqual(merged, [old])
        self.assertEqual(counts["new_machine_candidates"], 0)

    def test_disposition_conflicts_and_missing_ids_are_not_erased(self):
        with self.assertRaisesRegex(ValueError, "would be lost"):
            kb.merge_fact_dispositions([self.verified], self.dispositions)
        bad = copy.deepcopy(self.dispositions)
        bad["dispositions"][0]["page"] = 9
        with self.assertRaisesRegex(ValueError, "identity conflict"):
            kb.merge_fact_dispositions(self.previous, bad)

    def test_migration_dryrun_apply_and_repeat_are_safe(self):
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        dry = self.run_main("--migrate-facts", "--dry-run", "--migration-output", "stage")
        self.assertFalse((self.root / "stage").exists())
        applied = self.run_main("--migrate-facts", "--apply", "--migration-output", "stage")
        self.assertEqual(dry["counts"], applied["counts"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})
        with self.assertRaisesRegex(ValueError, "non-existing"):
            self.run_main("--migrate-facts", "--apply", "--migration-output", "stage")
        staged = json.loads((self.root / "stage/evidence_facts.json").read_text(encoding="utf-8"))
        repeated, _ = kb.merge_preserved_facts(kb.fact_candidates(self.doc["pages"], self.doc["source_id"]), staged)
        self.assertEqual(staged, repeated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
