from datetime import date, datetime, timezone, timedelta
from threading import Event
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fireatlas.assistant.board_views import heatmap_catalog, requests_heatmap_catalog
from fireatlas.assistant.contracts import digest
from fireatlas.assistant.firms_country import answer, is_heatmap_request, resolve
from fireatlas.studio.board_views import render


class CountryViewTests(unittest.TestCase):
    def test_catalog_lists_addable_saved_studies(self):
        self.assertTrue(requests_heatmap_catalog("What heatmaps can you bring?"))
        self.assertFalse(requests_heatmap_catalog("Can you show a heatmap of Park Fire?"))
        self.assertEqual([row["label"] for row in heatmap_catalog()["view_options"]],
                         ["Park Fire", "Camp Fire", "Grove Fire"])

    def test_country_scope_and_sensor_are_explicit(self):
        self.assertEqual(resolve("Give me thermal readings from Bangladesh for the last 3 days"),
                         (("BGD", "Bangladesh"), 3, "VIIRS_NOAA20_NRT"))
        self.assertEqual(resolve("Show me MODIS thermal readings in Japan")[-1], "MODIS_NRT")
        question = "Provide heatmap for Bangladesh"
        self.assertEqual(resolve(question), (("BGD", "Bangladesh"), 3, "VIIRS_NOAA20_NRT"))
        self.assertTrue(is_heatmap_request(question))
        with self.assertRaisesRegex(ValueError, "one country"):
            resolve("Show thermal readings in Bangladesh and India")
        self.assertEqual(resolve("Show thermal readings in Bangladesh in 2024")[1],
                         (date(2024,1,1),date(2024,12,31)))
        self.assertIsNone(resolve("Show a heatmap of Park Fire on 2024-07-27."))

    def test_area_rows_are_clipped_before_freezing(self):
        # Dhaka and Agartala are both within the queried extent, but only
        # Dhaka is inside Bangladesh.
        day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
        csv = ("latitude,longitude,bright_ti4,acq_date,acq_time,frp\n"
               f"23.81,90.41,313.2,{day},144,2.2\n"
               f"23.83,91.28,330.2,{day},144,3.1\n")
        saved = []
        service = SimpleNamespace(store=SimpleNamespace(
            artifact=lambda owner, kind, body: saved.append(body) or "result"))
        request = resolve("Show thermal readings in Bangladesh")
        with patch("fireatlas.assistant.firms_country.firms_key", return_value="test-key"), \
             patch("fireatlas.assistant.firms_country.fetch._download", return_value=csv):
            result = answer(service, "owner", request, Event(), time.monotonic() + 5)
        payload = saved[0]["payload"]
        self.assertEqual(payload["detections"], 1)
        self.assertEqual(payload["maximum_brightness_k"], 313.2)
        self.assertEqual(payload["records"][0]["acquisition_utc"], f"{day}T01:44+00:00")
        self.assertEqual(result["kind"], "Live NASA FIRMS")
        self.assertEqual(result["data_views"], [{"kind": "firms-country", "result_id": "result"}])
        self.assertEqual(saved[0]["sha256"], digest({key: value for key, value in saved[0].items() if key != "sha256"}))

    def test_country_heatmap_bins_all_rows_from_its_verified_receipt(self):
        day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
        csv = ("latitude,longitude,bright_ti4,acq_date,acq_time,frp\n"
               f"23.81,90.41,313.2,{day},144,2.2\n"
               f"23.81,90.41,310.2,{day},253,2.1\n"
               f"23.83,91.28,330.2,{day},144,3.1\n")
        saved = []
        service = SimpleNamespace(store=SimpleNamespace(
            artifact=lambda owner, kind, body: saved.append(body) or "result"))
        request = resolve("Provide heatmap for Bangladesh")
        with patch("fireatlas.assistant.firms_country.firms_key", return_value="test-key"), \
             patch("fireatlas.assistant.firms_country.fetch._download", return_value=csv):
            result = answer(service, "owner", request, Event(), time.monotonic() + 5, heatmap=True)
        kind = result["data_views"][0]["kind"]
        self.assertEqual(kind, "firms-country-heatmap")
        receipt = saved[0]
        self.assertEqual(receipt["context"]["bbox"], receipt["payload"]["query_bbox"])
        preview = render({"scope": receipt["context"], "snapshot_sha256": "hash"}, receipt, kind)
        self.assertIn("<polygon ", preview["svg"])
        self.assertEqual(preview["visual"]["total"], 2)
        self.assertEqual([cell["count"] for cell in preview["visual"]["cells"]], [2])
