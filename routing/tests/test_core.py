"""Tests for the Django-free core. Run with:  python -m unittest routing.tests.test_core"""
import itertools
import random
import unittest

from routing.errors import InfeasibleRoute
from routing.geo import cumulative_miles, decode_polyline, haversine_mi
from routing.optimizer import plan_fuel_stops
from routing.stations import RouteStation, Station, StationIndex


def rs(pos, price, off=0.0, sid=None):
    sid = sid if sid is not None else int(pos * 1000)
    return RouteStation(Station(sid, f"S{sid}", "addr", "City", "TX", 0.0, 0.0, price), pos, off)


class GeoTests(unittest.TestCase):
    def test_polyline_google_example(self):
        pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(pts, [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])

    def test_haversine_chicago_la(self):
        d = haversine_mi(41.8781, -87.6298, 34.0522, -118.2437)
        self.assertAlmostEqual(d, 1745, delta=10)

    def test_cumulative(self):
        pts = [(40.0, -100.0), (40.0, -99.0), (40.0, -98.0)]
        cum = cumulative_miles(pts)
        self.assertEqual(cum[0], 0.0)
        self.assertAlmostEqual(cum[2], 2 * cum[1], places=6)


class OptimizerTests(unittest.TestCase):
    def test_short_trip_needs_no_stops(self):
        plan = plan_fuel_stops([rs(100, 3.0)], total_miles=400)
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost, 0)

    def test_buys_only_enough_to_reach_cheaper_station(self):
        # 1000 mi trip, start full (500). The cheap station at 600 is out of reach
        # from the start, so stop at 400 (arrive with 100 mi left) and buy only the
        # 100 mi needed to reach 600, then buy the final 400 mi at the cheap price.
        plan = plan_fuel_stops([rs(400, 4.0), rs(600, 3.0)], total_miles=1000)
        self.assertEqual([s.route_station.along_mi for s in plan.stops], [400, 600])
        self.assertAlmostEqual(plan.stops[0].gallons, 10.0)
        self.assertAlmostEqual(plan.stops[1].gallons, 40.0)
        self.assertAlmostEqual(plan.total_cost, 10 * 4.0 + 40 * 3.0)

    def test_fills_up_at_cheap_station_when_nothing_cheaper_ahead(self):
        plan = plan_fuel_stops([rs(300, 3.0), rs(700, 4.0)], total_miles=1200)
        # At 300 (cheapest), fill to 500 range -> reaches 800; 700 is pricier so
        # buy at 300 as much as possible: tank had 200, so +300mi = 30 gal.
        first = plan.stops[0]
        self.assertEqual(first.route_station.along_mi, 300)
        self.assertAlmostEqual(first.gallons, 30.0)
        self.assertAlmostEqual(first.cost, 90.0)

    def test_infeasible_gap(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([rs(100, 3.0)], total_miles=1000)

    def test_ignores_station_beyond_destination(self):
        # Only station is past the destination: 600 mi trip can't be done on 500.
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([rs(1100, 1.0)], total_miles=600)

    def test_total_gallons_matches_distance(self):
        plan = plan_fuel_stops([rs(p, 3.0 + (p % 7) / 10) for p in range(100, 2000, 150)], 2000)
        self.assertAlmostEqual(plan.total_gallons, (2000 - 500) / 10, places=6)


def brute_force_cost(stations, total, R, mpg):
    """Try every subset of stations as stop set with 'buy just enough to reach the
    next chosen stop' economics solved by DP over fuel levels in 1-mile steps."""
    pts = sorted(stations, key=lambda s: s[0]) + [(total, 0.0)]
    # DP over (node index, fuel in whole miles)
    INF = float("inf")
    best = {(-1, R): 0.0}
    pos = {-1: 0}
    for i, (p, _) in enumerate(pts):
        pos[i] = p
    for i in range(len(pts)):
        nxt = {}
        for (j, f), c in best.items():
            f2 = f - (pts[i][0] - pos[j])
            if f2 < 0:
                continue
            f2 = int(round(f2))
            # decide to buy b miles here
            price = pts[i][1]
            for b in range(0, R - f2 + 1):
                key = (i, f2 + b)
                cost = c + b / mpg * price
                if cost < nxt.get(key, INF):
                    nxt[key] = cost
        best = nxt
    return min(best.values()) if best else INF


class OptimizerVsBruteForce(unittest.TestCase):
    def test_random_instances(self):
        rnd = random.Random(7)
        for _ in range(60):
            R, mpg = 50, 10.0
            total = rnd.randint(60, 220)
            positions = sorted(rnd.sample(range(1, total), rnd.randint(3, 9)))
            stations = [(p, round(rnd.uniform(2.5, 5.0), 3)) for p in positions]
            try:
                plan = plan_fuel_stops([rs(p, pr) for p, pr in stations], total, range_miles=R, mpg=mpg)
            except InfeasibleRoute:
                self.assertEqual(brute_force_cost(stations, total, R, mpg), float("inf"))
                continue
            self.assertAlmostEqual(plan.total_cost, brute_force_cost(stations, total, R, mpg), places=6,
                                   msg=f"{total=} {stations=}")


class CorridorTests(unittest.TestCase):
    def test_selects_only_stations_near_route_and_orders_them(self):
        # Straight west->east route at lat 40 from -100 to -90 (~530 mi)
        pts = [(40.0, -100.0 + i * 0.05) for i in range(201)]
        cum = cumulative_miles(pts)
        near_far = Station(1, "far-along", "", "", "KS", 40.02, -91.0, 3.0)
        near_early = Station(2, "early", "", "", "KS", 39.98, -99.0, 3.1)
        off = Station(3, "too-far-north", "", "", "KS", 41.0, -95.0, 1.0)  # ~69 mi off
        idx = StationIndex([near_far, near_early, off])
        got = idx.along_route(pts, cum, corridor_mi=10)
        self.assertEqual([g.station.id for g in got], [2, 1])
        self.assertLess(got[0].along_mi, got[1].along_mi)
        self.assertLessEqual(got[0].off_route_mi, 10)

    def test_rejects_oversized_corridor(self):
        with self.assertRaises(ValueError):
            StationIndex([]).along_route([(0, 0)], [0.0], corridor_mi=50)


if __name__ == "__main__":
    unittest.main()
