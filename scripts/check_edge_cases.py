"""Run edge cases against a RUNNING server and print PASS/FAIL for each.

    python manage.py runserver            (terminal 1)
    python scripts/check_edge_cases.py    (terminal 2)

Optional: python scripts/check_edge_cases.py http://127.0.0.1:8000
Needs internet (the first request for each new route calls OSRM).
"""
import json
import sys
import time

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/route/"
results = []

try:
    requests.get(BASE + "/", timeout=10)
except requests.RequestException:
    sys.exit(f"Cannot reach {BASE}. Start the server first:  python manage.py runserver")


def legs_ok(body, max_range):
    """Every gap between consecutive stops (and start/finish) must be <= range."""
    stops = body["fuel_stops"]
    marks = [s["mile_marker"] for s in stops]
    if marks != sorted(marks):
        return "mile markers not ascending"
    pts = [0.0] + marks + [body["route"]["distance_miles"]]
    worst = max(b - a for a, b in zip(pts, pts[1:]))
    return None if worst <= max_range + 0.6 else f"leg of {worst:.0f} mi exceeds range {max_range}"


def cost_ok(body):
    total = sum(s["cost"] for s in body["fuel_stops"])
    return None if abs(total - body["total_fuel_cost"]) <= 0.05 + 0.01 * len(body["fuel_stops"]) \
        else f"stop costs sum to {total:.2f} but total is {body['total_fuel_cost']}"


def run(name, method="GET", params=None, json_body=None, raw_body=None, expect=(200,), check=None, path=""):
    t0 = time.perf_counter()
    try:
        if method == "GET":
            r = requests.get(API + path, params=params, timeout=90)
        elif raw_body is not None:
            r = requests.request(method, API, data=raw_body, headers={"Content-Type": "application/json"}, timeout=90)
        elif json_body is not None:
            r = requests.request(method, API, json=json_body, timeout=90)
        else:
            r = requests.request(method, API, params=params, timeout=90)
    except requests.RequestException as exc:
        results.append((name, False, f"could not reach server: {exc}", 0))
        return None
    dt = time.perf_counter() - t0
    problems = []
    if r.status_code not in expect:
        problems.append(f"status {r.status_code}, expected {expect}: {r.text[:150]}")
    body = None
    if not problems and check:
        try:
            body = r.json() if "json" in r.headers.get("Content-Type", "") else r.text
            msg = check(body)
            if msg:
                problems.append(msg)
        except Exception as exc:  # a failing check shouldn't stop the run
            problems.append(f"check crashed: {exc!r}")
    detail = f"HTTP {r.status_code}"
    if isinstance(body, dict) and "fuel_stops" in body:
        detail += (f", {body['route']['distance_miles']} mi, {len(body['fuel_stops'])} stops, "
                   f"${body['total_fuel_cost']}")
    results.append((name, not problems, "; ".join(problems) or detail, dt))
    return r


def stops_plan(rng=500):
    def check(b):
        return legs_ok(b, rng) or cost_ok(b)
    return check


def no_stops(b):
    return None if b["fuel_stops"] == [] and b["total_fuel_cost"] == 0 else "expected no stops and $0"


def error_mentions(text):
    return lambda b: None if text.lower() in json.dumps(b).lower() else f"error should mention {text!r}: {b}"


# ---- normal trips -------------------------------------------------------
run("Long trip: Chicago -> Los Angeles", params={"start": "Chicago, IL", "finish": "Los Angeles, CA"},
    check=stops_plan())
run("Longest-ish N-S: Seattle -> Miami", params={"start": "Seattle, WA", "finish": "Miami, FL"},
    check=stops_plan())
run("East coast: Boston -> Atlanta", params={"start": "Boston, MA", "finish": "Atlanta, GA"}, check=stops_plan())
run("Sparse west: Salt Lake City -> Las Vegas", params={"start": "Salt Lake City, UT", "finish": "Las Vegas, NV"},
    check=stops_plan())
run("Short trip (<500 mi): Dallas -> Austin", params={"start": "Dallas, TX", "finish": "Austin, TX"}, check=no_stops)
run("Same start and finish", params={"start": "Dallas, TX", "finish": "Dallas, TX"}, expect=(200, 400))

# ---- input formats ------------------------------------------------------
run("Lowercase, no space: chicago,il -> Denver, Colorado",
    params={"start": "chicago,il", "finish": "Denver, Colorado"}, check=stops_plan())
run("No comma: Dallas TX -> Austin TX", params={"start": "Dallas TX", "finish": "Austin TX"}, check=no_stops)
run("Trailing country: Dallas, TX, USA", params={"start": "Dallas, TX, USA", "finish": "Austin, TX"}, check=no_stops)
run("Big city alias: New York, NY -> Chicago, IL", params={"start": "New York, NY", "finish": "Chicago, IL"},
    check=stops_plan())
run("St. Louis, MO -> Nashville, TN", params={"start": "St. Louis, MO", "finish": "Nashville, TN"})
run("Raw coordinates", params={"start": "41.8781,-87.6298", "finish": "39.7392,-104.9903"}, check=stops_plan())
run("Mixed city + coordinates", params={"start": "Dallas, TX", "finish": "30.2672,-97.7431"}, check=no_stops)

# ---- bad input -> clean 400 --------------------------------------------
run("Missing finish", params={"start": "Dallas, TX"}, expect=(400,))
run("Missing both", params={}, expect=(400,))
run("Unknown city", params={"start": "Nowhere, TX", "finish": "Dallas, TX"}, expect=(400,),
    check=error_mentions("Nowhere"))
run("Unknown state code", params={"start": "Dallas, ZZ", "finish": "Austin, TX"}, expect=(400,))
run("City with no state", params={"start": "Dallas", "finish": "Austin, TX"}, expect=(400,))
run("Outside USA: London coordinates", params={"start": "51.5074,-0.1278", "finish": "Dallas, TX"}, expect=(400,))
run("Swapped lng,lat", params={"start": "-87.6298,41.8781", "finish": "Dallas, TX"}, expect=(400,))
run("Alaska city", params={"start": "Anchorage, AK", "finish": "Seattle, WA"}, expect=(400,))
run("Hawaii city", params={"start": "Honolulu, HI", "finish": "Los Angeles, CA"}, expect=(400,))
run("Non-numeric mpg", params={"start": "Dallas, TX", "finish": "Austin, TX", "mpg": "abc"}, expect=(400,))
run("Range too small", params={"start": "Dallas, TX", "finish": "Austin, TX", "range_miles": 10}, expect=(400,))
run("Corridor too wide", params={"start": "Dallas, TX", "finish": "Austin, TX", "corridor_miles": 50}, expect=(400,))
run("Negative mpg", params={"start": "Dallas, TX", "finish": "Austin, TX", "mpg": -5}, expect=(400,))

# ---- options ------------------------------------------------------------
run("Empty tank at start -> 422", params={"start": "Dallas, TX", "finish": "Austin, TX", "starting_fuel_miles": 0},
    expect=(422,))
run("Smaller range 300 mi: Chicago -> Denver",
    params={"start": "Chicago, IL", "finish": "Denver, CO", "range_miles": 300}, expect=(200, 422),
    check=lambda b: legs_ok(b, 300) if "fuel_stops" in b else None)
run("Better mpg (20) halves gallons",
    params={"start": "Chicago, IL", "finish": "Los Angeles, CA", "mpg": 20},
    check=lambda b: None if abs(b["total_gallons_purchased"] - (b["route"]["distance_miles"] - 500) / 20) < 0.3
    else f"gallons {b['total_gallons_purchased']} not (distance-500)/20")
run("geometry=false drops coordinates",
    params={"start": "Chicago, IL", "finish": "Los Angeles, CA", "geometry": "false"},
    check=lambda b: None if "geometry" not in b["route"] else "geometry still present")
run("Geometry present by default", params={"start": "Dallas, TX", "finish": "Austin, TX"},
    check=lambda b: None if b["route"].get("geometry", {}).get("type") == "LineString" else "no LineString")

# ---- HTTP methods and other endpoints -----------------------------------
run("POST JSON body", method="POST", json_body={"start": "Dallas, TX", "finish": "Austin, TX"}, check=no_stops)
run("POST invalid JSON", method="POST", raw_body="{not json", expect=(400,))
run("POST JSON array (not object)", method="POST", raw_body="[1,2]", expect=(400,))
run("PUT not allowed", method="PUT", params={"start": "Dallas, TX", "finish": "Austin, TX"}, expect=(405,))
run("DELETE not allowed", method="DELETE", expect=(405,))
run("Map page renders", path="map/", params={"start": "Dallas, TX", "finish": "Austin, TX"},
    check=lambda t: None if "leaflet" in t.lower() and "plan-data" in t else "map HTML missing leaflet/plan data")
run("Map page: bad city -> 400", path="map/", params={"start": "Nowhere, TX", "finish": "Dallas, TX"}, expect=(400,))
try:
    r = requests.get(BASE + "/no/such/page", timeout=20)
    results.append(("Unknown URL -> 404", r.status_code == 404, f"HTTP {r.status_code}", 0))
except requests.RequestException as exc:
    results.append(("Unknown URL -> 404", False, f"request failed: {exc}", 0))

# ---- caching / speed ----------------------------------------------------
p = {"start": "Chicago, IL", "finish": "Los Angeles, CA"}
try:
    t0 = time.perf_counter(); requests.get(API, params=p, timeout=90); first = time.perf_counter() - t0
    t0 = time.perf_counter(); requests.get(API, params=p, timeout=90); second = time.perf_counter() - t0
    results.append(("Repeat request is fast (cached)", second < 1.0, f"first {first:.2f}s, repeat {second:.2f}s", second))
except requests.RequestException as exc:
    results.append(("Repeat request is fast (cached)", False, f"request failed: {exc}", 0))

# ---- report ---------------------------------------------------------------
width = max(len(n) for n, *_ in results)
for name, ok, detail, dt in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {dt:5.2f}s  {detail}")
failed = [n for n, ok, *_ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("Failed:", "; ".join(failed))
    sys.exit(1)
