import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion"))
if Path("/app").exists():
    sys.path.insert(0, "/app")

from seed_demo_corpus import fill_corpus  # noqa: E402


class FillCorpusTests(unittest.TestCase):
    def test_runs_real_ingestion_shape_until_target(self):
        stats = Mock(side_effect=[{"total": 9_900}, {"total": 9_960}, {"total": 10_020}, {"total": 10_020}])
        runner = Mock(return_value={"sources": [{"remaining": 5}]})

        result = fill_corpus(
            10_000, 10, stats_reader=stats, runner=runner,
            exhausted_reader=lambda: False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["runs"], 2)
        self.assertEqual(runner.call_args.args[0]["adapters"], ["masters_portal"])
        self.assertEqual(runner.call_args.args[0]["tier"], 1)

    def test_fails_when_catalog_exhausts_below_target(self):
        stats = Mock(side_effect=[{"total": 100}, {"total": 120}, {"total": 120}])
        runner = Mock(return_value={"sources": [{"remaining": 0}]})

        with self.assertRaisesRegex(RuntimeError, "stopped at 120"):
            fill_corpus(
                10_000, 10, stats_reader=stats, runner=runner,
                exhausted_reader=lambda: False,
            )

    def test_accepts_honest_catalog_limit_above_configured_minimum(self):
        stats = Mock(side_effect=[{"total": 7_000}, {"total": 7_989}, {"total": 7_989}])
        runner = Mock(return_value={"sources": [{"remaining": 0}]})

        result = fill_corpus(
            10_000, 10, 7_500, stats_reader=stats, runner=runner,
            exhausted_reader=lambda: False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["catalog_exhausted"])

    def test_returns_immediately_when_sufficient_catalog_is_already_exhausted(self):
        stats = Mock(return_value={"total": 7_989})
        runner = Mock()

        result = fill_corpus(
            10_000, 10, 7_500, stats_reader=stats, runner=runner,
            exhausted_reader=lambda: True,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["runs"], 0)
        self.assertTrue(result["catalog_exhausted"])
        stats.assert_called_once_with()
        runner.assert_not_called()

    def test_returns_immediately_at_demo_minimum_without_claiming_exhaustion(self):
        stats = Mock(return_value={"total": 8_001})
        runner = Mock()

        result = fill_corpus(
            10_000, 10, 7_500, stats_reader=stats, runner=runner,
            exhausted_reader=lambda: False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["ready_reason"], "minimum_reached")
        self.assertFalse(result["catalog_exhausted"])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
