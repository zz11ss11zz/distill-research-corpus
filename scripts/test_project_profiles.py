"""Isolated cross-material profile and shared-engine regressions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from corpus_profile import load_profile, master_paths
import distill_complete_knowledge_base as core


class ProjectProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="corpus_profile_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = {
            "schema_version": 1, "material_system": "battery fixture",
            "canonical_roots": {"paper": "literature", "dataset": "data"},
            "keyword_groups": {"capacity": "specific capacity"},
            "formula_pattern": r"\bLiFePO4\b",
            "value_unit_pattern": r"\d+(?:\.\d+)?\s*mAh\s*g-1",
            "evidence_rules": {"candidate_status": "source_located_not_human_verified"},
        }
        for name in ("config", "literature", "data"):
            (self.root/name).mkdir()
        (self.root/"literature/paper.txt").write_text(
            "LiFePO4 delivered a specific capacity of 155 mAh g-1 at 0.1 C.\n\n"
            "The hypothetical material retained its cycling response after repeated cycling.", encoding="utf-8")
        (self.root/"data/measurements.csv").write_text("material,value\nLiFePO4,155\n",encoding="utf-8")
        self.write_profile()

    def write_profile(self):
        (self.root/"config/research-corpus.json").write_text(json.dumps(self.profile),encoding="utf-8")

    def run_script(self, script, *args):
        result = subprocess.run([sys.executable,"-B",str(Path(__file__).parent/script),"--root",str(self.root),*args],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def read(self,name):
        return json.loads((self.root/"outputs/json/knowledge_distillation"/name).read_text(encoding="utf-8"))

    def test_end_to_end_battery_profile_and_cache_invalidation(self):
        self.run_script("preflight_corpus.py")
        self.run_script("run_incremental_distillation.py")
        facts=self.read("evidence_facts.json")
        self.assertEqual(len(facts),1)
        self.assertIn("155 mAh g-1",facts[0]["numeric_value_candidates"])
        self.assertEqual(facts[0]["material_formula_candidates"],["LiFePO4"])
        self.assertEqual(facts[0]["verification_status"],"source_located_not_human_verified")
        self.assertEqual(self.read("tabular_data_manifest.json")["converted_file_count"],1)
        first_version=self.read("manifest.json")["quality_model"]["fact_extraction_version"]
        source_id=facts[0]["source_id"]
        self.run_script("run_incremental_distillation.py")
        self.assertEqual(self.read("manifest.json")["statistics"]["document_records_extracted"],0)
        self.profile["keyword_groups"]["cycling"]="cycling"
        self.write_profile()
        self.run_script("distill_complete_knowledge_base.py")
        stats=self.read("manifest.json")["statistics"]
        self.assertEqual(stats["document_records_extracted"],0)
        self.assertEqual(stats["fact_sources_refreshed"],1)
        self.assertNotEqual(first_version,self.read("manifest.json")["quality_model"]["fact_extraction_version"])
        facts=self.read("evidence_facts.json")
        self.assertEqual(len(facts),2)
        self.assertEqual({f["source_id"] for f in facts},{source_id})

    def test_distinct_material_rules_and_no_cross_profile_theme_leak(self):
        core.configure_profile(self.root)
        pages=[{"page":1,"text":"An FeNi alloy had a measured yield strength of 600 MPa under the specified tensile test."}]
        self.assertEqual(core.fact_candidates(pages,"source"),[])
        self.profile.update(material_system="alloy fixture",formula_pattern=r"\bFeNi\b",value_unit_pattern=r"\d+\s*MPa",keyword_groups={"strength":"yield strength"})
        self.write_profile();core.configure_profile(self.root)
        facts=core.fact_candidates(pages,"source")
        self.assertEqual(facts[0]["numeric_value_candidates"],["600 MPa"])
        self.assertEqual(facts[0]["themes"],["strength"])

    def test_invalid_scope_regex_and_evidence_status_fail_closed(self):
        original=copy.deepcopy(self.profile)
        for key,value in [("canonical_roots",{"paper":"../outside"}),
                          ("canonical_roots",{"paper":"literature","dataset":"literature/nested"}),
                          ("formula_pattern","["),
                          ("evidence_rules",{"candidate_status":"human_verified"})]:
            self.profile=copy.deepcopy(original);self.profile[key]=value;self.write_profile()
            with self.assertRaises((ValueError, __import__('re').error)):
                load_profile(self.root)

    def test_master_index_rejects_changed_content(self):
        output=self.root/"out";output.mkdir()
        (self.root/"master.json").write_text("{}")
        (output/"master_collections.json").write_text(json.dumps({"collections":[{"database_type":"experiment","path":"master.json","sha256":"bad"}]}))
        profile={"master_sources":[{"path":"master.json","existing_index_type":"experiment"}]}
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            master_paths(profile,self.root,output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
