"""Cost-minimising fuel stop selection. No Django imports.

This is the classic "gas station problem" on a line. The greedy rule below is
optimal for it: at each station, look ahead as far as one full tank can go.

* If a station that is cheaper (or equal) lies within range, buy just enough
  to reach it.
* Otherwise this is the cheapest fuel in range, so fill the tank (or buy only
  what the destination needs if it is within range).

The destination is modelled as a zero-priced sentinel station, which makes
"buy only what is needed to finish" fall out of the first rule.
"""
from dataclasses import dataclass

from .errors import InfeasibleRoute
from .stations import RouteStation

EPS = 1e-6


@dataclass(frozen=True, slots=True)
class FuelStop:
    route_station: RouteStation
    gallons: float
    cost: float


@dataclass(frozen=True, slots=True)
class FuelPlan:
    stops: list
    total_cost: float
    total_gallons: float


def plan_fuel_stops(candidates, total_miles, range_miles=500.0, mpg=10.0, initial_miles=None):
    """Return the cheapest set of purchases that gets from mile 0 to `total_miles`.

    `candidates` are RouteStation objects. `initial_miles` is the range already
    in the tank at the start (default: a full tank). That initial fuel is not
    billed, because the brief gives no price for it.
    """
    if initial_miles is None:
        initial_miles = range_miles
    initial_miles = min(initial_miles, range_miles)

    # An empty tank means the vehicle cannot buy fuel at the origin; the first
    # purchasable station must be away from the start.
    if initial_miles <= EPS:
        candidates = [c for c in candidates if c.along_mi > EPS]

    # (position, price, RouteStation|None); None is the destination sentinel.
    nodes = [(c.along_mi, c.station.price, c) for c in sorted(candidates, key=lambda c: c.along_mi)
             if 0 <= c.along_mi < total_miles]
    nodes.append((total_miles, 0.0, None))

    fuel = initial_miles  # miles of range currently in the tank
    pos = 0.0
    stops = []
    n = len(nodes)

    for i, (npos, price, rs) in enumerate(nodes):
        fuel -= npos - pos
        if fuel < -EPS:
            raise InfeasibleRoute(
                f"No fuel station within {range_miles:.0f} miles of mile {pos:.0f}; "
                f"the next reachable point is {npos - pos:.0f} miles away."
            )
        pos = npos
        if rs is None:
            break

        target = None
        for j in range(i + 1, n):
            if nodes[j][0] - pos > range_miles + EPS:
                break
            if nodes[j][1] <= price:
                target = j
                break
        need = (nodes[target][0] - pos) if target is not None else min(range_miles, total_miles - pos)
        buy_miles = max(0.0, need - fuel)
        if buy_miles > EPS:
            gallons = buy_miles / mpg
            stops.append(FuelStop(rs, gallons, gallons * price))
            fuel += buy_miles

    total_cost = sum(s.cost for s in stops)
    total_gallons = sum(s.gallons for s in stops)
    return FuelPlan(stops, total_cost, total_gallons)
