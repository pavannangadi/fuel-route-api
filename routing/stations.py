"""Station storage, spatial index and the route-corridor query. No Django imports."""
import json
import math
from collections import defaultdict
from dataclasses import dataclass

from .geo import approx_dist_mi

CELL_DEG = 0.5
MAX_CORRIDOR_MI = 20.0  # must stay below one grid cell (~23 mi wide at 49N)


@dataclass(frozen=True, slots=True)
class Station:
    id: int
    name: str
    address: str
    city: str
    state: str
    lat: float
    lon: float
    price: float  # USD per gallon


@dataclass(frozen=True, slots=True)
class RouteStation:
    station: Station
    along_mi: float  # miles from the start, measured along the route
    off_route_mi: float  # straight-line distance from the route


def _cell(lat, lon):
    return (math.floor(lat / CELL_DEG), math.floor(lon / CELL_DEG))


class StationIndex:
    def __init__(self, stations):
        self.stations = list(stations)
        self._cells = defaultdict(list)
        for s in self.stations:
            self._cells[_cell(s.lat, s.lon)].append(s)

    @classmethod
    def from_json(cls, path):
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        return cls(Station(**row) for row in rows)

    def along_route(self, points, cum_miles, corridor_mi, sample_step_mi=1.0):
        """Stations within `corridor_mi` of the route, ordered by position along it.

        Route vertices are thinned to roughly one per `sample_step_mi`, bucketed
        into the same grid as the stations, and each candidate station is only
        compared with samples in its own and neighbouring cells. For a coast to
        coast route that is a few hundred thousand cheap distance checks.
        """
        if corridor_mi > MAX_CORRIDOR_MI:
            raise ValueError(f"corridor must be <= {MAX_CORRIDOR_MI} miles")

        samples, last = [], None
        for (lat, lon), m in zip(points, cum_miles):
            if last is None or m - last >= sample_step_mi:
                samples.append((lat, lon, m))
                last = m
        if samples and samples[-1][2] != cum_miles[-1]:
            lat, lon = points[-1]
            samples.append((lat, lon, cum_miles[-1]))

        sample_cells = defaultdict(list)
        for lat, lon, m in samples:
            sample_cells[_cell(lat, lon)].append((lat, lon, m))

        candidate_cells = set()
        for (cy, cx) in sample_cells:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    candidate_cells.add((cy + dy, cx + dx))

        found = []
        for key in candidate_cells:
            for st in self._cells.get(key, ()):
                cy, cx = key
                best = None
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        for lat, lon, m in sample_cells.get((cy + dy, cx + dx), ()):
                            d = approx_dist_mi(st.lat, st.lon, lat, lon)
                            if d <= corridor_mi and (best is None or d < best[0]):
                                best = (d, m)
                if best:
                    found.append(RouteStation(st, best[1], best[0]))
        found.sort(key=lambda r: r.along_mi)
        return found
