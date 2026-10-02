import unittest

from fireatlas.provenance import public_source_reference, sanitize_public_payload


class ReplayProvenanceTests(unittest.TestCase):
    def test_local_file_reference_hides_machine_path_and_keeps_project_path(self):
        value = "file:///home/user/Desktop/project/NASA_data/heatmap_inputs/firms/park.csv"

        self.assertEqual(
            public_source_reference(value),
            "local-file:NASA_data/heatmap_inputs/firms/park.csv",
        )

    def test_remote_and_archive_identifiers_are_preserved(self):
        for value in (
            "https://example.test/archive/file.csv",
            "urn:fireatlas:nasa-firms-archive:123:sha256:abc",
        ):
            with self.subTest(value=value):
                self.assertEqual(public_source_reference(value), value)

    def test_nested_public_payload_sanitizes_all_local_file_references(self):
        result = sanitize_public_payload({"inputs": [{"source_uri": "file:///home/user/raw.csv"}]})

        self.assertEqual(result["inputs"][0]["source_uri"], "local-file:raw.csv")


if __name__ == "__main__":
    unittest.main()
