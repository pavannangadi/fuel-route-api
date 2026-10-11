"""Django-free tests for the data build and the planner.
Run with:  python -m unittest routing.tests.test_pipeline"""
import io
import unittest
from pathlib import Path

from routing import build
from routing.geo import haversine_mi
from routing.planner import build_plan
from routing.stations import Station, StationIndex

CSV = """OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
1,A STOP,"I-80, EXIT 1",St. Louis,MO,1,3.50
1,A STOP #1,"I-80, EXIT 1",St. Louis,MO,1,3.20
2,CANADIAN,"HWY 1",Calgary,AB,2,1.50
3,B STOP,"US-30",Tiny Town,NE,3,3.00
"""

GEONAMES = "\n".join([
    # id, name, ascii, alt, lat, lon, class, code, cc, cc2, admin1, admin2, a3, a4, pop
    "1\tSaint Louis\tSaint Louis\t\t38.627\t-90.199\tP\tPPLA2\tUS\t\tMO\t\t\t\t300000",
    "2\tTiny Town\tTiny Town\t\t40.0\t-99.0\tP\tPPL\tUS\t\tNE\t\t\t\t0",
    "3\tOtherville\tOtherville\t\t41.0\t-98.0\tP\tPPL\tUS\t\tNE\t\t\t\t50",
    "4\tBig Hill\tBig Hill\t\t30.0\t-97.0\tH\tHLL\tUS\t\tTX\t\t\t\t0",
])


class BuildTests(unittest.TestCase):
    def test_norm_city_variants_match(self):
        self.assertEqual(build.norm_city("St. Louis"), build.norm_city("Saint Louis"))
        self.assertEqual(build.norm_city("Ft. Worth"), "fort worth")

    def test_csv_drops_non_us_and_dedupes_to_cheapest(self):
        stations, skipped = build.read_fuel_csv(io.StringIO(CSV))
        self.assertEqual(skipped, 1)
        self.assertEqual({s["id"] for s in stations}, {1, 3})
        self.assertEqual(next(s for s in stations if s["id"] == 1)["price"], 3.20)

    def test_geonames_parse_and_geocode(self):
        stations, _ = build.read_fuel_csv(io.StringIO(CSV))
        wanted = {build.place_key(s["city"], s["state"]) for s in stations}
        places = build.parse_geonames_us(GEONAMES.splitlines(), wanted)
        self.assertIn("saint louis|MO", places)
        self.assertIn("tiny town|NE", places)          # wanted, though population 0
        self.assertNotIn("otherville|NE", places)      # unwanted and tiny
        located, missing = build.geocode_stations(stations, places)
        self.assertEqual((len(located), len(missing)), (2, 0))


class RealCsvTests(unittest.TestCase):
    CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "fuel-prices-for-be-assessment.csv"

    @unittest.skipUnless(CSV_PATH.exists(), "fuel CSV not present")
    def test_real_csv_loads(self):
        with open(self.CSV_PATH, newline="", encoding="utf-8") as fh:
            stations, skipped = build.read_fuel_csv(fh)
        self.assertGreater(len(stations), 5000)
        self.assertGreater(skipped, 0)  # Canadian rows exist in the file
        self.assertTrue(all(2.0 < s["price"] < 8.0 for s in stations))


class PlannerTests(unittest.TestCase):
    def test_end_to_end_on_synthetic_cross_country_route(self):
        # ~1,700-mile straight route with a station every ~40 miles; prices vary.
        n = 1700
        points = [(37.0, -120.0 + i * 0.0145) for i in range(n)]  # ~0.0145 deg lon ~ 0.8 mi
        total = sum(haversine_mi(*points[i], *points[i + 1]) for i in range(n - 1))
        route = {"distance_mi": total, "duration_h": total / 60, "points": points}
        stations = [
            Station(i, f"S{i}", "addr", "City", "NV", 37.0 + (i % 3 - 1) * 0.02, -120.0 + i * 0.58,
                    3.0 + ((i * 7) % 11) / 10)
            for i in range(1, 1700 // 40)
        ]
        idx = StationIndex(stations)
        loc = {"label": "x", "lat": 0, "lon": 0}
        plan = build_plan(loc, loc, route, idx, corridor_mi=10, range_mi=500, mpg=10, initial_mi=500)

        self.assertGreaterEqual(len(plan.get("fuel_stops")), 2)
        marks = [s["mile_marker"] for s in plan["fuel_stops"]]
        self.assertEqual(marks, sorted(marks))
        # No leg may exceed the vehicle range.
        legs = [0.0] + marks + [plan["route"]["distance_miles"]]
        self.assertTrue(all(b - a <= 500.5 for a, b in zip(legs, legs[1:])))
        # Gallons bought = (distance - starting range) / mpg; cost = sum of stops.
        self.assertAlmostEqual(plan["total_gallons_purchased"], (total - 500) / 10, delta=0.2)
        self.assertAlmostEqual(plan["total_fuel_cost"], sum(s["cost"] for s in plan["fuel_stops"]), delta=0.05)
        self.assertEqual(plan["route"]["geometry"]["type"], "LineString")


if __name__ == "__main__":
    unittest.main()
