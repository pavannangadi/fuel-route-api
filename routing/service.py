"""Django-aware orchestration: settings, caching, lazy data loading."""
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from . import osrm
from .errors import DataNotBuilt
from .gazetteer import resolve_location
from .planner import build_plan
from .stations import StationIndex


@lru_cache(maxsize=1)
def get_index():
    try:
        return StationIndex.from_json(settings.STATIONS_PATH)
    except FileNotFoundError as exc:
        raise DataNotBuilt("stations.json not found. Run `python manage.py build_stations` first.") from exc


def plan_trip(start_text, finish_text, *, range_mi, mpg, corridor_mi, initial_mi):
    """Resolve both ends, fetch ONE route, pick fuel stops. Results are cached so
    repeat requests (and the map page that follows the JSON call) make no
    upstream call at all."""
    s_lat, s_lon, s_label = resolve_location(start_text, settings.PLACES_PATH)
    f_lat, f_lon, f_label = resolve_location(finish_text, settings.PLACES_PATH)

    key = "plan:{:.3f},{:.3f}:{:.3f},{:.3f}:{}:{}:{}:{}".format(
        s_lat, s_lon, f_lat, f_lon, range_mi, mpg, corridor_mi, initial_mi)
    plan = cache.get(key)
    if plan is not None:
        return plan

    start = {"label": s_label, "lat": s_lat, "lon": s_lon}
    finish = {"label": f_label, "lat": f_lat, "lon": f_lon}
    route = osrm.fetch_route(settings.OSRM_BASE_URL, (s_lat, s_lon), (f_lat, f_lon),
                             timeout=settings.ROUTING_TIMEOUT)
    plan = build_plan(start, finish, route, get_index(), corridor_mi=corridor_mi,
                      range_mi=range_mi, mpg=mpg, initial_mi=initial_mi)
    cache.set(key, plan, settings.PLAN_CACHE_SECONDS)
    return plan
