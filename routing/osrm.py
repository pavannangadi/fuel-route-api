"""Routing client. One HTTP call per uncached route.

Uses the free OSRM demo server (no API key). Point OSRM_BASE_URL at your own
OSRM instance for production, since the demo server is fair-use only.
"""
import requests

from .errors import BadRequest, RoutingUnavailable
from .geo import decode_polyline

_session = requests.Session()
METERS_PER_MILE = 1609.344


def fetch_route(base_url, start, finish, timeout=15):
    """start/finish are (lat, lon). Returns dict(distance_mi, duration_h, points)."""
    coords = f"{start[1]:.6f},{start[0]:.6f};{finish[1]:.6f},{finish[0]:.6f}"
    try:
        resp = _session.get(
            f"{base_url}/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "polyline", "steps": "false", "alternatives": "false"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RoutingUnavailable(f"Routing service unreachable: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise RoutingUnavailable(f"Routing service returned HTTP {resp.status_code}") from exc

    code = data.get("code")
    if code in ("NoRoute", "NoSegment"):
        raise BadRequest("No drivable route found between those locations.")
    if code != "Ok" or not data.get("routes"):
        raise RoutingUnavailable(f"Routing service error: {code or resp.status_code}")

    route = data["routes"][0]
    return {
        "distance_mi": route["distance"] / METERS_PER_MILE,
        "duration_h": route["duration"] / 3600,
        "points": decode_polyline(route["geometry"], precision=5),
    }
