"""Django-free tests for location parsing and edge cases.
Run with:  python -m unittest routing.tests.test_gazetteer"""
import json
import tempfile
import unittest
from pathlib import Path

from routing.errors import BadRequest
from routing.gazetteer import resolve_location, _load_places
from routing.planner import build_plan
from routing.stations import StationIndex

PLACES = {
    "dallas|TX": [32.78, -96.80],
    "austin|TX": [30.27, -97.74],
    "new york city|NY": [40.71, -74.01],
    "saint louis|MO": [38.63, -90.20],
    "kansas city|MO": [39.10, -94.58],
    "charleston|WV": [38.35, -81.63],
    "anchorage|AK": [61.22, -149.90],
    "honolulu|HI": [21.31, -157.86],
}


class ResolveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp())
        cls.path = d / "places.json"
        cls.path.write_text(json.dumps(PLACES))
        _load_places.cache_clear()

    def ok(self, text):
        return resolve_location(text, self.path)

    def test_formats_that_should_work(self):
        for text in ["Dallas, TX", "dallas,tx", "  Dallas ,  Texas ", "Dallas TX", "Dallas Texas",
                     "Dallas, TX, USA", "Dallas, TX, United States", "Dallas, Tx."]:
            lat, lon, _ = self.ok(text)
            self.assertEqual((lat, lon), (32.78, -96.80), text)

    def test_city_suffix_and_abbreviations(self):
        self.assertEqual(self.ok("New York, NY")[:2], (40.71, -74.01))       # stored as "New York City"
        self.assertEqual(self.ok("New York City, NY")[:2], (40.71, -74.01))
        self.assertEqual(self.ok("St. Louis, MO")[:2], (38.63, -90.20))
        self.assertEqual(self.ok("Kansas City MO")[:2], (39.10, -94.58))
        self.assertEqual(self.ok("Charleston West Virginia")[:2], (38.35, -81.63))

    def test_coordinates(self):
        self.assertEqual(self.ok("41.85, -87.65")[:2], (41.85, -87.65))
        self.assertEqual(self.ok("41.85,-87.65")[:2], (41.85, -87.65))

    def test_rejections(self):
        for text in ["", "   ", "Dallas", "Nowhere, TX", "Dallas, ZZ", "London, UK",
                     "51.5,-0.12",          # London
                     "-87.65,41.85",        # lng,lat swapped
                     "19.7,-155.1",         # Hawaii coordinates
                     "Anchorage, AK", "Honolulu, HI"]:
            with self.assertRaises(BadRequest, msg=text):
                self.ok(text)


class DegenerateRouteTests(unittest.TestCase):
    def test_zero_length_route_has_no_stops(self):
        pts = [(41.85, -87.65), (41.85, -87.65)]
        route = {"distance_mi": 0.0, "duration_h": 0.0, "points": pts}
        loc = {"label": "x", "lat": 0, "lon": 0}
        plan = build_plan(loc, loc, route, StationIndex([]), corridor_mi=10, range_mi=500, mpg=10, initial_mi=500)
        self.assertEqual(plan["fuel_stops"], [])
        self.assertEqual(plan["total_fuel_cost"], 0)

    def test_single_point_route(self):
        route = {"distance_mi": 0.0, "duration_h": 0.0, "points": [(41.85, -87.65)]}
        loc = {"label": "x", "lat": 0, "lon": 0}
        plan = build_plan(loc, loc, route, StationIndex([]), corridor_mi=10, range_mi=500, mpg=10, initial_mi=500)
        self.assertEqual(plan["fuel_stops"], [])


if __name__ == "__main__":
    unittest.main()
