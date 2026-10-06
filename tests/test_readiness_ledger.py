"""Reporting integrity checks; these are not private SaaS acceptance tests."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("readiness_validator", ROOT / "tools/verify_readiness_ledger.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class TestReadinessLedger(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(validator.LEDGER.read_text(encoding="utf-8"))

    def test_current_ledger_has_consistent_provenance(self):
        self.assertEqual(validator.validate(self.data), [])

    def test_duplicate_cohort_is_rejected(self):
        self.data["independent_cohorts"].append(copy.deepcopy(self.data["independent_cohorts"][0]))
        self.assertIn("duplicate cohort", validator.validate(self.data))

    def test_peer_claim_cannot_be_counted_as_independent(self):
        self.data["independent_cohorts"][0]["kind"] = "peer_reported_pytest"
        self.assertIn("peer evidence mislabeled as independent", validator.validate(self.data))

    def test_counts_refuse_booleans_and_negative_values(self):
        self.data["independent_cohorts"][0]["passed"] = True
        self.data["independent_cohorts"][1]["failed"] = -1
        self.assertIn("invalid assertion count", validator.validate(self.data))

    def test_build_and_receipt_hash_are_required(self):
        self.data["independent_cohorts"][0]["build"] = "latest"
        self.data["independent_cohorts"][1]["evidence_sha256"] = ""
        self.assertIn("missing exact provenance", validator.validate(self.data))

    def test_unaccepted_release_cannot_be_marked_complete(self):
        self.data["full_platform_release_accepted"] = True
        self.assertIn("release claimed with unaccepted cases", validator.validate(self.data))

    def test_aggregate_product_test_total_is_rejected(self):
        self.data["total_product_tests"] = 9999
        self.assertIn("ambiguous aggregate count", validator.validate(self.data))


if __name__ == "__main__":
    unittest.main()
