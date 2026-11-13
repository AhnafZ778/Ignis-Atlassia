import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
import threading
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error
from calendar import monthrange
from datetime import date

from fireatlas.comparability import analyze, complete_months, digest, evaluate, source_switch, verify
from fireatlas.comparison_evidence import confusion


def inputs(years=range(2020, 2025), factor=3):
    days = []
    for year in years:
        for month in range(1, 13):
            for day in range(1, monthrange(year, month)[1] + 1):
                m = 5 + month + day % 3
                days.append({"date": date(year, month, day).isoformat(), "sources": {
                    "MODIS_SP": {"cells": m, "raw": m + 1, "versions": ["61.03"], "verified_export": True, "processing_gap": False},
                    "VIIRS_SNPP_SP": {"cells": m * factor, "raw": m * factor + 1, "versions": ["2"], "verified_export": True, "processing_gap": False},
                }})
    return {"schema": "fireatlas-comparability-input-v1", "region": "norcal", "days": days}


class ComparabilityTests(unittest.TestCase):
    def test_partial_months_and_outages_are_wholly_excluded(self):
        i = inputs([2024])
        i["days"] = i["days"][1:]
        next(d for d in i["days"] if d["date"] == "2024-07-24")["sources"]["VIIRS_SNPP_SP"]["processing_gap"] = True
        next(d for d in i["days"] if d["date"] == "2024-06-01")["sources"]["MODIS_SP"]["verified_export"] = False
        rows, excluded = complete_months(i)
        self.assertEqual(len(rows), 9)
        reasons = {r["month"]: r["reasons"] for r in excluded}
        self.assertIn("missing-utc-dates", reasons["2024-01"])
        self.assertIn("documented-processing-gap", reasons["2024-07"])
        self.assertIn("unverified-or-incomplete-source-export", reasons["2024-06"])
        self.assertEqual(next(r for r in rows if r["month"] == 2)["days"], 29)

    def test_collections_are_not_pooled(self):
        i = inputs()
        for d in i["days"]:
            if d["date"].startswith("2020"):
                d["sources"]["MODIS_SP"]["versions"] = ["6.03"]
        r = analyze(i)
        self.assertEqual(r["versions"], ["61.03", "2"])
        self.assertEqual(r["eligibility"]["complete_matched_months"], 48)
        self.assertFalse(r["admission"]["historical_collection_transfer"])
        i["versions"] = ["6.03", "2"]
        r = analyze(i)
        self.assertEqual(r["eligibility"]["complete_matched_months"], 12)
        self.assertFalse(r["admission"]["monthly_comparison"])

    def test_outer_test_values_cannot_fit_or_select_their_model(self):
        rows, _ = complete_months(inputs())
        first = evaluate(rows, "nested")
        changed = copy.deepcopy(rows)
        for r in changed:
            if r["year"] == 2023:
                r["viirs"] *= 17
        second = evaluate(changed, "nested")
        a = [r for r in first["rows"] if r["year"] == 2023]
        b = [r for r in second["rows"] if r["year"] == 2023]
        self.assertEqual([(r["factor"], r["model"], r["prediction"]) for r in a],
                         [(r["factor"], r["model"], r["prediction"]) for r in b])
        self.assertTrue(all(2023 not in r["training_years"] for r in a))

    def test_forward_never_uses_future_values(self):
        rows, _ = complete_months(inputs())
        before = evaluate(rows, "forward")
        changed = copy.deepcopy(rows)
        for r in changed:
            if r["year"] >= 2023:
                r["viirs"] *= 50
        after = evaluate(changed, "forward")
        a = [r for r in before["rows"] if r["year"] == 2022]
        b = [r for r in after["rows"] if r["year"] == 2022]
        self.assertEqual(a, b)
        self.assertTrue(all(max(r["training_years"]) < r["year"] for r in before["rows"]))

    def test_full_year_metric_excludes_a_partial_month(self):
        i = inputs()
        next(d for d in i["days"] if d["date"] == "2024-07-01")["sources"]["VIIRS_SNPP_SP"]["processing_gap"] = True
        r = analyze(i)
        annuals = r["evaluation"]["nested"]["complete_year_results"]
        self.assertNotIn(2024, [a["year"] for a in annuals])

    def test_counterfactual_preserves_real_reference_change(self):
        rows, _ = complete_months(inputs())
        ev = evaluate(rows, "forward")
        switch = source_switch(ev, 2024, 7)
        self.assertTrue(switch["seam_evaluable"])
        self.assertAlmostEqual(switch["adjusted_seam_error"], 0)
        self.assertGreater(switch["raw_seam_error"], 0)
        by = {r["month"]: r for r in switch["rows"]}
        self.assertNotEqual(by[6]["reference"], by[7]["reference"])
        self.assertEqual(by[7]["adjusted_switch"], by[7]["reference"])
        self.assertIsNone(source_switch(ev, 2010, 7))

    def test_reproduction_rejects_rehashed_result_tampering(self):
        i = inputs()
        bundle = {"schema": "fireatlas-comparability-bundle-v1", "inputs": i, "result": analyze(i)}
        self.assertTrue(verify(bundle)["verified"])
        bundle["result"]["admission"]["daily_imputation"] = True
        bundle["result"].pop("result_sha256")
        bundle["result"]["result_sha256"] = digest(bundle["result"])
        with self.assertRaisesRegex(ValueError, "recount"):
            verify(bundle)

    def test_unknown_and_zero_remain_distinct_and_imputation_closed(self):
        i = inputs([2024])
        i["days"][0]["sources"]["MODIS_SP"].update(cells=0, raw=0)
        r = analyze(i)
        self.assertEqual(r["zero_recovery_limit"]["modis_zero_viirs_positive_days"], 1)
        self.assertFalse(r["admission"]["daily_imputation"])
        self.assertFalse(r["admission"]["monthly_comparison"])
        i["days"][0]["sources"]["MODIS_SP"].update(cells=None, raw=None)
        rows, excluded = complete_months(i)
        self.assertIn("unknown-source-total", excluded[0]["reasons"])

    def test_invalid_count_versions_and_dates_fail_closed(self):
        for mutation in (
            lambda i: i["days"].append(i["days"][0]),
            lambda i: i["days"][0]["sources"]["MODIS_SP"].update(cells=float("nan")),
            lambda i: i["days"][0]["sources"]["MODIS_SP"].update(cells=True),
            lambda i: i["days"][0]["sources"]["MODIS_SP"].update(versions="61.03"),
            lambda i: i["days"][0].update(date="20240101"),
        ):
            i = inputs([2024])
            mutation(i)
            with self.assertRaises((ValueError, TypeError)):
                complete_months(i)

    def test_http_comparison_rejects_invalid_scope_and_preserves_empty_evidence(self):
        from fireatlas.core import connect
        from fireatlas.web import handler_factory
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "science.sqlite3"
            with connect(database):
                pass
            handler = handler_factory(database)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                for path in ("/api/comparability?region=custom", "/api/comparability/case?case=unknown", "/api/comparability?demo=1"):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(base + path)
                    self.assertEqual(caught.exception.code, 400)
                with urllib.request.urlopen(base + "/api/comparability?region=norcal") as response:
                    value = json.load(response)
                self.assertTrue(verify(value)["verified"])
                self.assertEqual(value["result"]["eligibility"]["complete_matched_months"], 0)
                self.assertFalse(value["result"]["admission"]["monthly_comparison"])
                self.assertIsNone(value["result"]["evaluation"]["nested"]["raw"]["median_absolute_log_error"])
                with urllib.request.urlopen(base + "/api/comparability/case?case=grove-2025") as response:
                    self.assertEqual(json.load(response)["case_id"], "grove-2025")
                with urllib.request.urlopen(base + "/harmonization.html") as response:
                    self.assertIn(b"comparison-route.js", response.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                handler.assistant.close()
                if handler.studio is not None:
                    handler.studio.close()

    def test_published_comparison_and_cases_recount_from_their_inputs(self):
        from fireatlas.comparison_evidence import build_case
        root = Path(__file__).resolve().parents[1] / "site/data/comparability"
        manifest = json.loads((root / "manifest.json").read_text())
        for name, entry in manifest["files"].items():
            body = (root / name).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), entry["sha256"], name)
            self.assertEqual(len(body), entry["bytes"], name)
            value = json.loads(body)
            if name.startswith("cases/"):
                self.assertEqual(value, build_case(value["case_id"]), name)
            else:
                self.assertTrue(verify(value)["verified"], name)

    def test_assistant_metric_units_are_resolved_from_evidence(self):
        from fireatlas.assistant.agent import fact, guided_answer
        from fireatlas.assistant.contracts import METHODS
        result = analyze(inputs())
        evidence = {"id": "comparison-fixture", "release_id": "fixture", "operation": "comparability",
                    "method": METHODS["comparability"], "context": {}, "limitations": [],
                    "payload": {"schema": "fireatlas-comparability-bundle-v1", "result": result, "inputs": inputs()}}
        for path, unit in (
            ("/result/eligibility/complete_matched_months", "months"),
            ("/result/evaluation/nested/raw/n_months", "months"),
            ("/result/evaluation/nested/raw/median_absolute_log_error", "dimensionless log error"),
            ("/result/evaluation/nested/adjusted/relative_bias", "fraction"),
            ("/result/evaluation/nested/adjusted/median_absolute_percentage_error_nonzero", "fraction"),
            ("/result/evaluation/nested/rows/0/factor", "ratio"),
            ("/result/evaluation/nested/rows/0/raw_modis", "records"),
            ("/result/zero_recovery_limit/viirs_positive_days", "UTC days"),
            ("/inputs/days/0/sources/MODIS_SP/raw", "records"),
            ("/inputs/days/0/sources/MODIS_SP/cells", "cells"),
            ("/result/eligibility/years/0", "UTC calendar year"),
            ("/result/region/bbox/0", "degrees"),
            ("/result/admission/policy/minimum_relative_log_error_improvement", "fraction"),
        ):
            self.assertEqual(fact(evidence, path)["unit"], unit, path)
        evidence["payload"]["result"]["diagnostics"] = {"platform_daynight_inventory": [{"imported_rows": 17}]}
        self.assertEqual(fact(evidence, "/result/diagnostics/platform_daynight_inventory/0/imported_rows")["unit"], "records")
        evidence["payload"]["unregistered_numeric"] = 12
        with self.assertRaisesRegex(ValueError, "declared claim unit"):
            fact(evidence, "/unregistered_numeric")
        for card in guided_answer(evidence)["claims"]:
            self.assertEqual(card["unit"], fact(evidence, card["path"])["unit"])

    def test_positive_overlap_is_not_overall_agreement(self):
        pairs = [{"modis_state": "observed-without-detection", "viirs_state": "observed-without-detection"}] * 100
        pairs += [{"modis_state": "detected", "viirs_state": "detected"},
                  {"modis_state": "detected", "viirs_state": "observed-without-detection"},
                  {"modis_state": "observed-without-detection", "viirs_state": "detected"}]
        m = confusion(pairs)
        self.assertGreater(m["overall_agreement"], .98)
        self.assertEqual(m["positive_jaccard"], 1/3)
        self.assertEqual(m["positive_union_pairs"], 3)
        self.assertIsNone(confusion([])["positive_jaccard"])


if __name__ == "__main__":
    unittest.main()
