"""Observable regressions for context boundaries and conclusion references."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from corpus_profile import load_profile
import distill_complete_knowledge_base as core
from evidence_audit import build_context_checks, bind_conclusions, write_atomic


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="evidence_audit_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "literature").mkdir()
        self.raw_profile = {"schema_version": 1, "canonical_roots": {"paper": "literature"},
                            "formula_pattern": r"\bLiFePO4\b", "value_unit_pattern": r"\d+\s*mAh\s*g-1",
                            "keyword_groups": {"capacity": "specific capacity"},
                            "evidence_rules": {"candidate_status": "source_located_not_human_verified",
                                "required_context": ["temperature", "atmosphere", "cell_type", "source_page"],
                                "context_patterns": {"temperature": r"\d+\s*K\b", "atmosphere": r"\bin air\b"}}}
        (self.root / "config/research-corpus.json").write_text(json.dumps(self.raw_profile), encoding="utf-8")
        self.profile = load_profile(self.root)
        core.configure_profile(self.root)
        self.text = "😀 LiFePO4 delivered a specific capacity of 155 mAh g-1 at\n298 K.\n\nThe apparatus was kept in air."
        path = self.root / "literature/source.txt"
        path.write_text(self.text, encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        self.docs = [{"source_id": "source", "path": "literature/source.txt", "sha256": sha,
                      "pages": [{"page": 1, "text": self.text}]}]
        self.facts = core.fact_candidates(self.docs[0]["pages"], "source")
        self.input = {"schema_version": "1.0.0", "conclusions": [{"conclusion_id": "claim-1",
            "text": "The source reports a capacity measurement.", "claim_type": "source_fact",
            "evidence": [{"fact_id": self.facts[0]["fact_id"], "relation": "supports"}]}]}

    def bind(self, payload=None):
        return bind_conclusions(payload or self.input, self.facts, self.docs, self.profile, self.root)

    def test_context_scans_candidate_only_and_retains_unconfigured_fields(self):
        original = copy.deepcopy(self.facts)
        check = build_context_checks(self.facts, self.docs, self.profile)["records"][0]
        fields = {f["field"]: f for f in check["fields"]}
        self.assertEqual(fields["temperature"]["status"], "located_in_candidate")
        self.assertEqual(fields["atmosphere"]["status"], "not_located_in_candidate")
        self.assertEqual(fields["cell_type"]["status"], "not_configured")
        self.assertEqual(fields["source_page"]["status"], "located_in_cached_page")
        m = fields["temperature"]["matches"][0]
        self.assertEqual(self.facts[0]["evidence_text"][m["start"]:m["end"]], "298 K")
        self.assertEqual(self.facts, original)

    def test_invalid_context_profiles_fail_before_extraction(self):
        variants = [{"required_context": ["temperature", "temperature"]},
                    {"required_context": "temperature"},
                    {"context_patterns": {"unknown": "x"}},
                    {"context_patterns": {"temperature": "["}},
                    {"context_patterns": {"temperature": "x*"}},
                    {"context_patterns": {"source_page": "1"}}]
        for change in variants:
            with self.subTest(change=change):
                profile = copy.deepcopy(self.raw_profile)
                profile["evidence_rules"].update(change)
                (self.root / "config/research-corpus.json").write_text(json.dumps(profile), encoding="utf-8")
                with self.assertRaises((ValueError, __import__("re").error)):
                    load_profile(self.root)

    def test_legacy_context_without_patterns_remains_supported(self):
        self.profile["evidence_rules"].pop("context_patterns")
        checks = build_context_checks(self.facts, self.docs, self.profile)
        self.assertEqual(checks["statistics"]["field_status_counts"]["not_configured"], 3)

    def test_stale_legacy_locator_is_reported_without_erasing_verified_fact(self):
        self.facts[0]["evidence_text"] = "A retained verified summary outside machine text."
        self.facts[0]["verification_status"] = "human_verified"
        checks = build_context_checks(self.facts, self.docs, self.profile)
        self.assertEqual(checks["records"][0]["locator_status"], "locator_needs_review")
        self.assertEqual(checks["records"][0]["verification_status"], "human_verified")
        with self.assertRaises(ValueError):
            self.bind()

    def test_binding_checks_utf16_spans_and_never_promotes_candidates(self):
        result = self.bind()["conclusions"][0]
        self.assertEqual(result["support_state"], "supporting_facts_machine_candidates")
        self.assertEqual(result["binding_status"], "references_validated_not_conclusion_verified")
        self.assertEqual(result["evidence"][0]["page"], 1)
        self.assertEqual(self.facts[0]["verification_status"], "source_located_not_human_verified")

    def test_changed_source_bytes_block_binding(self):
        (self.root / "literature/source.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source bytes changed"):
            self.bind()

    def test_unknown_duplicate_and_background_only_links_fail(self):
        for evidence in [[{"fact_id": "missing", "relation": "supports"}],
                         self.input["conclusions"][0]["evidence"] * 2,
                         [{"fact_id": self.facts[0]["fact_id"], "relation": "context"}]]:
            payload = copy.deepcopy(self.input)
            payload["conclusions"][0]["evidence"] = evidence
            with self.assertRaises(ValueError):
                self.bind(payload)

    def test_human_and_agent_review_are_distinct(self):
        for status, expected in [("human_verified", "supporting_facts_human_verified"),
                                 ("agent_verified_page_anchored", "supporting_facts_agent_verified"),
                                 ("project_reviewed", "supporting_facts_mixed_or_project_specific_status")]:
            self.facts[0]["verification_status"] = status
            self.assertEqual(self.bind()["conclusions"][0]["support_state"], expected)
            self.assertEqual(self.bind()["conclusions"][0]["binding_status"], "references_validated_not_conclusion_verified")

    def test_inference_requires_rationale_and_conflict_is_preserved(self):
        other = {**copy.deepcopy(self.facts[0]), "fact_id": "other"}
        self.facts.append(other)
        claim = self.input["conclusions"][0]
        claim["claim_type"] = "inference"
        with self.assertRaisesRegex(ValueError, "rationale"):
            self.bind()
        claim["rationale"] = "An explicitly recorded inference for review."
        claim["evidence"].append({"fact_id": "other", "relation": "contradicts"})
        claim["conflicts"] = [{"fact_ids": [self.facts[0]["fact_id"], "other"], "description": "Declared conflicting interpretation."}]
        result = self.bind()["conclusions"][0]
        self.assertTrue(result["has_conflicting_evidence"])
        self.assertEqual(result["conflicts"], claim["conflicts"])
        claim["conflicts"][0]["fact_ids"][1] = "orphan"
        with self.assertRaisesRegex(ValueError, "Conflict"):
            self.bind()

    def test_bad_span_hash_and_page_fail(self):
        original = copy.deepcopy(self.facts)
        self.facts[0]["source_span"]["raw_text_sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "text hash"):
            self.bind()
        self.facts = original
        self.facts[0]["page"] = 2
        with self.assertRaisesRegex(ValueError, "page"):
            self.bind()

    def test_cli_staleness_and_failure_preserve_existing_output(self):
        output = self.root / "kb"
        write_atomic(output / "evidence_facts.json", self.facts)
        write_atomic(output / "documents.json", self.docs)
        write_atomic(self.root / "claims.json", self.input)
        cmd = [sys.executable, "-B", str(Path(__file__).with_name("bind_research_conclusions.py")),
               "--root", str(self.root), "--output", "kb", "--input", "claims.json"]
        def run(*extra):
            return subprocess.run(cmd + list(extra), capture_output=True, text=True, encoding="utf-8")
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        bound = output / "conclusion_bindings.json"
        before = bound.read_bytes()
        self.assertEqual(run("--validate-only").returncode, 0)
        self.input["conclusions"][0]["text"] = "Changed claim"
        write_atomic(self.root / "claims.json", self.input)
        self.assertNotEqual(run("--validate-only").returncode, 0)
        self.input["conclusions"][0]["evidence"][0]["fact_id"] = "missing"
        write_atomic(self.root / "claims.json", self.input)
        self.assertNotEqual(run().returncode, 0)
        self.assertEqual(bound.read_bytes(), before)
        self.assertEqual(list(output.glob("evidence_audit_*.tmp")), [])

    def test_cli_cannot_overwrite_fact_source_or_input(self):
        output = self.root / "kb"
        write_atomic(output / "evidence_facts.json", self.facts)
        write_atomic(output / "documents.json", self.docs)
        write_atomic(self.root / "claims.json", self.input)
        write_atomic(self.root / "unrelated.json", {"customer": "synthetic protected fixture"})
        for destination in ["kb/evidence_facts.json", "literature/source.txt", "literature/other.json",
                            "claims.json", "unrelated.json", "config/research-corpus.json", "../outside.json"]:
            before = (output / "evidence_facts.json").read_bytes()
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("bind_research_conclusions.py")),
                                     "--root", str(self.root), "--output", "kb", "--input", "claims.json",
                                     "--bound-output", destination], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / "evidence_facts.json").read_bytes(), before)

    def test_pipeline_emits_and_validates_context_checks(self):
        script = Path(__file__).with_name("run_incremental_distillation.py")
        cmd = [sys.executable, "-B", str(script), "--root", str(self.root)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.root / "outputs/json/knowledge_distillation"
        checks = json.loads((output / "context_checks.json").read_text(encoding="utf-8"))
        self.assertGreater(checks["statistics"]["facts"], 0)
        before = (output / "evidence_facts.json").read_bytes()
        profile = copy.deepcopy(self.raw_profile)
        profile["evidence_rules"]["context_patterns"]["temperature"] = r"\d+\s*°C"
        write_atomic(self.root / "config/research-corpus.json", profile)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((output / "evidence_facts.json").read_bytes(), before)
        checks = json.loads((output / "context_checks.json").read_text(encoding="utf-8"))
        self.assertEqual(checks["records"][0]["fields"][0]["status"], "not_located_in_candidate")
        checks["records"][0]["fields"][0]["status"] = "located_in_candidate"
        write_atomic(output / "context_checks.json", checks)
        result = subprocess.run([sys.executable, "-B", str(script.with_name("validate_knowledge_distillation.py")),
                                 "--root", str(self.root)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
