from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fireatlas.aggregates import daily_aggregates, write_paired_daily_bundle
from fireatlas.availability import source_status
from fireatlas.calibration import calibrate
from fireatlas.calendar_v2 import _verdict
from fireatlas.core import calendar as core_calendar, connect, ingest
from fireatlas.regions import REGIONS


FIELDS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
          "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"]


def _row(source: str, day: str, hhmm: str, kind: str = "0") -> list[str]:
    if source == "MODIS_SP":
        satellite, instrument, version = "Terra", "MODIS", "61.03"
    else:
        satellite, instrument, version = "SNPP", "SNPP", "2.0"
    return ["40", "-121", "300", "0.4", "0.4", day, hhmm, satellite, instrument,
            "n", version, "280", "2", "D", kind]


class AggregateAvailabilityTests(unittest.TestCase):
    def test_partial_archive_verdict_reports_source_counts_and_unknown_dates(self):
        verdict = _verdict("Northern California", 2010, {
            "month": "2010-07", "value": None, "n_years": 0,
            "partial_detection_days": 19,
            "partial_modis_cell_days": 97,
            "partial_viirs_cell_days": 0,
        })
        self.assertIn("97 MODIS and 0 S-NPP source cell-days", verdict)
        self.assertIn("across 19 UTC dates", verdict)
        self.assertIn("other dates are not zeros", verdict)

    def test_zero_exports_and_notices_are_not_called_sensor_pass_or_missing_fire(self):
        zero = source_status("2024-08-01", "VIIRS_SNPP_SP", complete_export=True, detection_count=0)
        self.assertEqual(zero["status"], "zero_detections_exported")
        self.assertEqual(zero["observation_opportunity"], "unknown")
        gap = source_status("2024-07-25", "VIIRS_SNPP_SP", complete_export=True, detection_count=0)
        self.assertEqual(gap["status"], "documented_processing_gap")
        self.assertEqual(gap["notice_ids"], ["snpp-2024-07-cdp-outage"])
        self.assertEqual(gap["notices"][0]["url"], "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716")
        self.assertEqual(gap["notice_day_scope"], "full-utc-day")
        endpoint = source_status("2024-07-24", "VIIRS_SNPP_SP", complete_export=True, detection_count=0)
        self.assertEqual(endpoint["notice_day_scope"], "partial-utc-day")
        detected = source_status("2024-08-02", "VIIRS_SNPP_SP", complete_export=True, detection_count=3)
        self.assertEqual(detected["status"], "detections_in_export")
        self.assertEqual(detected["observation_opportunity"], "unknown")
        self.assertEqual(source_status("2024-08-01", "VIIRS_SNPP_SP", complete_export=False,
                                       detection_count=0)["status"], "unknown_export")

    def test_daily_aggregate_excludes_type_two_and_preserves_zero_day(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "atlas.sqlite3"
            bbox = REGIONS["norcal"]["bbox"]
            for source in ("MODIS_SP", "VIIRS_SNPP_SP"):
                path = root / f"{source}.csv"
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(FIELDS)
                    if source == "MODIS_SP":
                        writer.writerow(_row(source, "2024-07-25", "1200", "0"))
                        type_two = _row(source, "2024-07-25", "1201", "2")
                        type_two[0] = "40.02"  # A separate grid cell must still stay out of the calendar.
                        writer.writerow(type_two)
                    else:
                        writer.writerow(_row(source, "2024-07-25", "1202", "0"))
                with connect(database) as db:
                    ingest(db, path, source, complete_month="2024-07", bbox=bbox)
            with connect(database) as db:
                data = daily_aggregates(db, "norcal", "2024-07-25", "2024-07-26")
                legacy = core_calendar(db, bbox=REGIONS["norcal"]["bbox"], year=2024, series="modis")
            first, second = data["days"]
            self.assertEqual(first["sources"]["MODIS_SP"]["raw_pixel_count"], 1)
            self.assertEqual(first["sources"]["MODIS_SP"]["detected_cell_days"], 1)
            legacy_july_25 = next(day for day in legacy["daily"] if day["date_utc"] == "2024-07-25")
            self.assertEqual(legacy_july_25["detected_cell_days"], 1)
            self.assertEqual(first["sources"]["VIIRS_SNPP_SP"]["raw_pixel_count"], 1)
            self.assertEqual(first["sources"]["VIIRS_SNPP_SP"]["availability"]["status"], "documented_processing_gap")
            self.assertEqual(first["sources"]["MODIS_SP"]["native_pixel_resolution_m"], 1000)
            self.assertEqual(first["sources"]["VIIRS_SNPP_SP"]["native_pixel_resolution_m"], 375)
            self.assertEqual(first["sensor_bridge"]["status"], "documented-processing-gap")
            self.assertIsNone(first["sensor_bridge"]["co_detected_cell_days"])
            self.assertEqual(first["sources"]["MODIS_SP"]["excluded_row_count"], 1)
            self.assertEqual(first["sources"]["MODIS_SP"]["excluded_type_counts"], {"2": 1})
            self.assertEqual(second["sources"]["MODIS_SP"]["raw_pixel_count"], 0)
            self.assertEqual(second["sources"]["VIIRS_SNPP_SP"]["raw_pixel_count"], 0)
            self.assertEqual(data["unit"], "distinct 1 km EASE-Grid centroid cell-days")

    def test_monthly_ratio_and_held_out_check_on_controlled_fixture(self):
        days = []
        for year in (2013, 2014):
            for month in range(1, 13):
                stamp = f"{year}-{month:02d}-15"
                source_data = {}
                for source, count, version in (("MODIS_SP", 30, "61.03"),
                                               ("VIIRS_SNPP_SP", 120, "2.0")):
                    source_data[source] = {
                        "export_complete": True,
                        "detected_cell_days": count,
                        "product_versions": [version],
                        "availability": {"status": "detections_in_export"},
                    }
                days.append({"date_utc": stamp, "sources": source_data})
        result = calibrate({"region": {"id": "norcal", "bbox": list(REGIONS["norcal"]["bbox"])}, "days": days})
        self.assertEqual(result["status"], "calibrated")
        self.assertEqual(result["annual_ratio"], 4)
        self.assertTrue(all(item["ratio"] == 4 for item in result["months"]))
        self.assertEqual(result["validation"]["models"]["monthly_ratio"]["median_absolute_log_error"], 0)

    def test_paired_bundle_contains_complete_month_only_and_tracks_parent_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "atlas.sqlite3"
            bbox = REGIONS["norcal"]["bbox"]
            for source in ("MODIS_SP", "VIIRS_SNPP_SP"):
                path = root / f"{source}.csv"
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(FIELDS)
                    if source == "MODIS_SP":
                        writer.writerow(_row(source, "2024-07-25", "1200", "0"))
                        writer.writerow(_row(source, "2024-07-25", "1201", "2"))
                    else:
                        writer.writerow(_row(source, "2024-07-25", "1202", "0"))
                parent = hashlib.sha256(f"parent-{source}".encode()).hexdigest()
                request = hashlib.sha256(f"request-{source}".encode()).hexdigest()
                uri = (f"urn:fireatlas:firms-archive:{source}:request-id:test-{source}"
                       f":parent-sha256:{parent}:request-sha256:{request}:region:norcal")
                with connect(database) as db:
                    result = ingest(db, path, source, source_uri=uri,
                                    complete_month="2024-07", bbox=bbox)
                    db.execute("""
                        INSERT INTO source_exports(
                          batch_id,region_id,source_id,month,request_start,request_end,
                          west,south,east,north,complete_export,coverage_basis,
                          product_versions_json,parent_sha256,request_sha256)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (result["batch_id"], "norcal", source, "2024-07",
                          "2024-07-01", "2024-07-31", *bbox, 1,
                          "request-metadata", json.dumps(["61.03" if source == "MODIS_SP" else "2.0"]),
                          parent, request))
            output = root / "norcal.json.gz"
            with connect(database) as db:
                result = write_paired_daily_bundle(db, "norcal", output)
            with gzip.open(output, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            self.assertEqual(payload["schema"], "fireatlas-daily-aggregates-v1")
            self.assertEqual(set(payload), {"schema", "method_version", "region", "generated_utc", "inputs", "days"})
            self.assertEqual(result["months"], 1)
            self.assertEqual(len(payload["days"]), 31)
            july_25 = next(day for day in payload["days"] if day["date"] == "2024-07-25")
            self.assertEqual(july_25["MODIS_SP"], {"cells": 1, "raw": 1, "frp_sum": 2.0,
                                                     "excluded": 1, "excluded_type_counts": {"2": 1}})
            self.assertEqual(july_25["VIIRS_SNPP_SP"], {"cells": 1, "raw": 1, "frp_sum": None,
                                                         "excluded": 0, "excluded_type_counts": {}})
            self.assertEqual(july_25["sensor_bridge"]["status"], "documented-processing-gap")
            self.assertEqual(len(payload["inputs"]), 2)
            self.assertTrue(all(len(item["sha256"]) == 64 for item in payload["inputs"]))


if __name__ == "__main__":
    unittest.main()
