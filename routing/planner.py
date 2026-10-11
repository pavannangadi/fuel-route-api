"""Combine a route with the station index and optimizer. No Django imports."""
from .geo import cumulative_miles
from .optimizer import plan_fuel_stops


def build_plan(start, finish, route, index, *, corridor_mi, range_mi, mpg, initial_mi, include_geometry=True):
    """`start`/`finish` are dicts with lat, lon, label; `route` comes from osrm.fetch_route."""
    points = route["points"]
    cum = cumulative_miles(points)
    # Vertex-to-vertex haversine slightly under/over-counts road distance; rescale
    # so positions along the route add up to the distance the router reported.
    scale = route["distance_mi"] / cum[-1] if cum[-1] else 1.0
    cum = [c * scale for c in cum]
    total = route["distance_mi"]

    candidates = index.along_route(points, cum, corridor_mi)
    plan = plan_fuel_stops(candidates, total, range_miles=range_mi, mpg=mpg, initial_miles=initial_mi)

    stops = []
    for n, s in enumerate(plan.stops, 1):
        st = s.route_station.station
        stops.append({
            "order": n,
            "station_id": st.id,
            "name": st.name,
            "address": st.address,
            "city": st.city,
            "state": st.state,
            "lat": st.lat,
            "lon": st.lon,
            "mile_marker": round(s.route_station.along_mi, 1),
            "distance_from_route_miles": round(s.route_station.off_route_mi, 1),
            "price_per_gallon": round(st.price, 3),
            "gallons_purchased": round(s.gallons, 2),
            "cost": round(s.cost, 2),
        })

    result = {
        # Key order matters for readability in Postman: the answer first, the
        # bulky route geometry last.
        "start": start,
        "finish": finish,
        "fuel_stops": stops,
        "total_gallons_purchased": round(plan.total_gallons, 2),
        "total_fuel_cost": round(plan.total_cost, 2),
        "assumptions": {
            "max_range_miles": range_mi,
            "miles_per_gallon": mpg,
            "starting_fuel_miles": initial_mi,
            "starting_fuel_is_billed": False,
            "corridor_miles": corridor_mi,
            "candidate_stations_on_route": len(candidates),
            "station_location": "city centroid (CSV has no coordinates)",
        },
        "route": {
            "distance_miles": round(total, 1),
            "duration_hours": round(route["duration_h"], 2),
        },
    }
    if include_geometry:
        result["route"]["geometry"] = {
            "type": "LineString",
            "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in points],
        }
    return result
