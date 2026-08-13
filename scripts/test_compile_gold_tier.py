import json
import tempfile
import unittest
from pathlib import Path

from compile_gold_tier import speaking_rows, strict_gate


class GoldTierCompilerTests(unittest.TestCase):
    def test_strict_gate_does_not_treat_exactly_eighty_as_above_eighty(self):
        self.assertFalse(strict_gate(0.8))
        self.assertTrue(strict_gate(0.80001))
        self.assertFalse(strict_gate(None))

    def test_speaking_accuracy_excludes_missing_overall_but_not_inaccurate_rows(self):
        manifest = {
            "items": [
                {
                    "item_id": "accurate",
                    "labels": {"validated": True, "overall_band": 6.5},
                    "permission": {"status": "granted"},
                },
                {
                    "item_id": "inaccurate",
                    "labels": {"validated": True, "overall_band": 8.0},
                    "permission": {"status": "granted"},
                },
                {
                    "item_id": "partial",
                    "labels": {"validated": True, "overall_band": 5.0},
                    "permission": {"status": "pending"},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item_id, band in (("accurate", 6.0), ("inaccurate", 7.0), ("partial", None)):
                payload = {
                    "evaluation": {
                        "evaluation_id": item_id,
                        "criteria": [{"status": "scored"}] * (3 if band is not None else 2),
                        "overall": {} if band is None else {"band": band},
                        "provenance": {"llm_model": "fixture-model"},
                    },
                    "latency_ms": 10,
                }
                (root / f"{item_id}.json").write_text(json.dumps(payload), encoding="utf-8")
            rows, accuracy = speaking_rows(manifest, root)

        self.assertEqual(len(rows), 3)
        self.assertEqual(accuracy, 0.5)
        self.assertIsNone(next(row for row in rows if row["item_id"] == "partial")["accurate"])


if __name__ == "__main__":
    unittest.main()
