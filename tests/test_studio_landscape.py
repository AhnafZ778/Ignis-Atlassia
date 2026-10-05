"""Supplied landscape backgrounds must retain exact footprint and provenance."""
import copy
import unittest
from unittest.mock import patch
from fireatlas.studio import context_layers
from fireatlas.studio.errors import StudioError


class LandscapeTests(unittest.TestCase):
    park = {'case': 'park-2024', 'bbox': [-122.0, 39.5, -121.3, 40.5]}

    def test_park_defaults_to_verified_vegetation_and_terrain(self):
        result = context_layers.landscape(self.park)
        self.assertEqual(result['selected'], 'ndvi')
        self.assertEqual([l['name'] for l in result['layers']], ['terrain', 'ndvi'])
        self.assertIn('2024-07-11', result['label'])
        context_layers.verify(result['layers'], self.park)

    def test_other_cases_use_their_own_terrain_not_park_vegetation(self):
        for case, bounds in [('camp-2018', [-121.85, 39.6, -121.3, 40.0]), ('grove-2025', [-121.55, 39.25, -121.28, 39.48])]:
            result = context_layers.landscape({'case': case, 'bbox': bounds})
            self.assertEqual(result['selected'], 'terrain')
            self.assertNotIn('ndvi', result['available'])

    def test_background_cannot_relabel_a_partial_footprint_as_regional_vegetation(self):
        result = context_layers.landscape({**self.park, 'bbox': [-122.2, 38.8, -120, 41]}, 'ndvi')
        self.assertEqual(result['layers'], [])
        self.assertEqual(result['selected'], 'none')
        self.assertIn('unavailable', result['note'])

    def test_heat_only_and_invalid_choice(self):
        result = context_layers.landscape(self.park, 'none')
        self.assertEqual(result['layers'], [])
        self.assertIn('ndvi', result['available'])
        with self.assertRaises(StudioError): context_layers.landscape(self.park, '../credentials')

    def test_missing_or_altered_image_keeps_heat_available(self):
        inventory = copy.deepcopy(context_layers.catalog())
        inventory['layers']['park-2024']['ndvi']['sha256'] = '0' * 64
        with patch.object(context_layers, 'catalog', return_value=inventory):
            result = context_layers.landscape(self.park)
        self.assertEqual(result['layers'], [])
        self.assertEqual(result['selected'], 'none')
        self.assertIn('Heat remains available', result['note'])

    def test_embedded_landscape_verification_rejects_changed_bytes(self):
        result = context_layers.landscape(self.park)
        result['layers'][0]['data'] = result['layers'][1]['data']
        with self.assertRaises(StudioError): context_layers.verify(result['layers'], self.park)
