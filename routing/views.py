import copy
import json
from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .errors import BadRequest, DataNotBuilt, InfeasibleRoute, RoutingUnavailable
from .service import plan_trip
from .stations import MAX_CORRIDOR_MI


def _params(request):
    if request.method == "POST" and request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except ValueError as exc:
            raise BadRequest("Body is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise BadRequest("JSON body must be an object.")
        return body
    return request.POST if request.method == "POST" else request.GET


def _number(params, name, default, lo, hi):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"{name} must be a number.") from exc
    if not lo <= value <= hi:
        raise BadRequest(f"{name} must be between {lo} and {hi}.")
    return value


def _plan_from_request(request):
    p = _params(request)
    range_mi = _number(p, "range_miles", settings.VEHICLE_RANGE_MILES, 50, 2000)
    return (
        plan_trip(
            str(p.get("start", "")),
            str(p.get("finish", "")),
            range_mi=range_mi,
            mpg=_number(p, "mpg", settings.VEHICLE_MPG, 1, 100),
            corridor_mi=_number(p, "corridor_miles", settings.CORRIDOR_MILES, 1, MAX_CORRIDOR_MI),
            # Default: leave with a full tank. Initial fuel is not billed.
            initial_mi=_number(p, "starting_fuel_miles", range_mi, 0, range_mi),
        ),
        p,
    )


def _error(exc):
    mapping = {
        BadRequest: 400,
        InfeasibleRoute: 422,
        RoutingUnavailable: 502,
        DataNotBuilt: 503,
    }
    return JsonResponse({"error": str(exc)}, status=mapping[type(exc)])


_ERRORS = (BadRequest, InfeasibleRoute, RoutingUnavailable, DataNotBuilt)


@require_http_methods(["GET"])
def index(request):
    """GET /  ->  short description and example links, so the root URL isn't a 404."""
    example = "start=Chicago, IL&finish=Los Angeles, CA"
    return JsonResponse({
        "service": "Fuel Route API",
        "endpoints": {
            "route_json": request.build_absolute_uri(reverse("route-api")) + "?" + example,
            "route_map": request.build_absolute_uri(reverse("route-map")) + "?" + example,
        },
        "inputs": "start and finish as 'City, ST' or 'lat,lng'",
    }, json_dumps_params={"indent": 2})


@require_http_methods(["GET", "POST"])
def route_api(request):
    """GET/POST /api/route/  with start, finish  ->  route, fuel stops, total cost."""
    try:
        plan, p = _plan_from_request(request)
    except _ERRORS as exc:
        return _error(exc)

    plan = copy.deepcopy(plan)  # the cached copy is shared; don't mutate it
    if str(p.get("geometry", "true")).lower() in ("0", "false", "no"):
        plan["route"].pop("geometry", None)
    query = urlencode({
        "start": f"{plan['start']['lat']},{plan['start']['lon']}",
        "finish": f"{plan['finish']['lat']},{plan['finish']['lon']}",
    })
    map_url = request.build_absolute_uri(reverse("route-map")) + "?" + query
    return JsonResponse({"map_url": map_url, **plan})  # map_url first for readability


@require_http_methods(["GET"])
def route_map(request):
    """GET /api/route/map/?start=..&finish=..  ->  HTML map of the route and fuel stops."""
    try:
        plan, _ = _plan_from_request(request)
    except _ERRORS as exc:
        return _error(exc)
    return render(request, "routing/map.html", {"plan": plan})
