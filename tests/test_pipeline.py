"""Offline tests: run with `python -m unittest discover -s tests -v` (no network)."""
from __future__ import annotations

import json
import re
import unittest

import numpy as np

from nut import build, leadlag
from nut.config import ROOT, Paths
from nut.thesis import PLACEHOLDER


class TestLeadLag(unittest.TestCase):
    def test_detects_a_real_lead(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=200)
        y = np.r_[0.0, 0.8 * x[:-1]] + 0.3 * rng.normal(size=200)
        r = leadlag.shift_pvalue(y, x, p=2, min_shift=8)
        self.assertLess(r["p_value"], 0.02)

    def test_no_lead_in_noise(self):
        rng = np.random.default_rng(1)
        r = leadlag.shift_pvalue(rng.normal(size=120), rng.normal(size=120), p=2, min_shift=8)
        self.assertGreater(r["p_value"], 0.05)

    def test_holm(self):
        self.assertEqual(leadlag.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics, _ = build.compute(Paths(ROOT))

    def test_core_metrics_are_finite(self):
        m = self.metrics
        for v in [
            m["issuance"]["rpc_annualized_issuance"],
            m["issuance"]["burn_to_fee_ratio"],
            m["capture"]["d90"]["coverage_total"],
            m["breakeven"]["multiple"],
        ]:
            self.assertIsNotNone(v)
            self.assertTrue(np.isfinite(v))

    def test_onchain_issuance_matches_protocol_parameter(self):
        # measured issuance can only be at or below max_inflation_rate (validator uptime reduces rewards)
        m = self.metrics
        self.assertLessEqual(m["issuance"]["rpc_annualized_issuance"], m["protocol"]["max_inflation_rate_float"] * 1.001)
        self.assertGreater(m["issuance"]["rpc_annualized_issuance"], m["protocol"]["max_inflation_rate_float"] * 0.9)

    def test_indexer_supply_matches_rpc(self):
        self.assertLess(self.metrics["issuance"]["supply_check_max_abs_rel_diff"], 0.001)

    def test_committed_metrics_match_rebuild(self):
        committed = json.loads((ROOT / "docs" / "metrics.json").read_text())
        fresh = build.analysis.strip_private(self.metrics)
        self.assertAlmostEqual(committed["capture"]["d90"]["coverage_total"], fresh["capture"]["d90"]["coverage_total"], places=12)
        self.assertEqual(committed["as_of"], fresh["as_of"])

    def test_thesis_has_no_unfilled_placeholders(self):
        text = (ROOT / "THESIS.md").read_text()
        self.assertIsNone(PLACEHOLDER.search(text))
        for section in ("## Claim", "## Evidence for", "## Evidence against", "## What would change our mind"):
            self.assertIn(section, text)

    def test_every_chart_has_sentence_source_and_file(self):
        html = (ROOT / "docs" / "index.html").read_text()
        for c in self.metrics.get("charts") or json.loads((ROOT / "docs" / "metrics.json").read_text())["charts"]:
            self.assertTrue((ROOT / "docs" / "charts" / f"{c['id']}.svg").exists(), c["id"])
            self.assertIn(f"charts/{c['id']}.svg", html)
            self.assertGreater(len(c["sentence"]), 40)
        self.assertGreaterEqual(len(re.findall(r"<b>Source:</b>", html)), 10)


if __name__ == "__main__":
    unittest.main()
