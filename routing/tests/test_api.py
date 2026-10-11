"""Django view tests. The routing service is mocked, so no network is needed.
Run with:  python manage.py test"""
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from routing import service
from routing.geo import haversine_mi

_tmp = Path(tempfile.mkdtemp())

# Dallas -> roughly 900 miles east-west line at lat 33; stations every ~50 mi.
_POINTS = [(33.0, -97.0 + i * 0.0145) for i in range(1100)]
_DIST = sum(haversine_mi(*_POINTS[i], *_POINTS[i + 1]) for i in range(len(_POINTS) - 1))
_STATIONS = [
    {"id": i, "name": f"STOP {i}", "address": "I-20", "city": "Town", "state": "TX",
     "lat": 33.0, "lon": -97.0 + i * 0.72, "price": round(3.0 + (i % 5) / 10, 3)}
    for i in range(1, 22)
]
(_tmp / "stations.json").write_text(json.dumps(_STATIONS))
(_tmp / "places.json").write_text(json.dumps({"dallas|TX": [33.0, -97.0], "farville|TX": [33.0, -81.0]}))


def _fake_route(*_a, **_k):
    return {"distance_mi": _DIST, "duration_h": _DIST / 60, "points": _POINTS}


@override_settings(STATIONS_PATH=_tmp / "stations.json", PLACES_PATH=_tmp / "places.json")
class RouteApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        service.get_index.cache_clear()
        from routing import gazetteer
        gazetteer._load_places.cache_clear()

    @mock.patch("routing.osrm.fetch_route", side_effect=_fake_route)
    def test_returns_route_stops_and_cost(self, fetch):
        r = self.client.get("/api/route/", {"start": "Dallas, TX", "finish": "Farville, TX"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(len(body["fuel_stops"]), 1)
        self.assertEqual(body["route"]["geometry"]["type"], "LineString")
        self.assertAlmostEqual(body["total_fuel_cost"], sum(s["cost"] for s in body["fuel_stops"]), delta=0.05)
        self.assertIn("/api/route/map/", body["map_url"])
        self.assertEqual(fetch.call_count, 1)

    @mock.patch("routing.osrm.fetch_route", side_effect=_fake_route)
    def test_repeat_request_makes_no_upstream_call(self, fetch):
        for _ in range(3):
            self.client.get("/api/route/", {"start": "Dallas, TX", "finish": "Farville, TX"})
        self.client.get("/api/route/map/", {"start": "Dallas, TX", "finish": "Farville, TX"})
        self.assertEqual(fetch.call_count, 1)

    @mock.patch("routing.osrm.fetch_route", side_effect=_fake_route)
    def test_post_json_and_geometry_off(self, _):
        r = self.client.post("/api/route/", data={"start": "Dallas, TX", "finish": "Farville, TX", "geometry": False},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("geometry", r.json()["route"])

    def test_missing_input_is_400(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 400)

    def test_unknown_city_is_400(self):
        r = self.client.get("/api/route/", {"start": "Nowhere, TX", "finish": "Dallas, TX"})
        self.assertEqual(r.status_code, 400)

    def test_outside_usa_is_400(self):
        r = self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "Dallas, TX"})
        self.assertEqual(r.status_code, 400)

    @mock.patch("routing.osrm.fetch_route", side_effect=_fake_route)
    def test_infeasible_range_is_422(self, _):
        # Empty tank at the start and the first station is ~42 miles away.
        r = self.client.get("/api/route/", {"start": "Dallas, TX", "finish": "Farville, TX", "starting_fuel_miles": 0})
        self.assertEqual(r.status_code, 422)

    @mock.patch("routing.osrm.fetch_route", side_effect=_fake_route)
    def test_map_page_renders(self, _):
        r = self.client.get("/api/route/map/", {"start": "Dallas, TX", "finish": "Farville, TX"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "plan-data")
