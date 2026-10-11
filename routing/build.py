"""Offline data build: fuel CSV + GeoNames -> stations.json and places.json.

The CSV has no coordinates, so each station is placed at the centroid of its
city/state using the free GeoNames gazetteer. This runs once, offline, so the
request path never geocodes anything. No Django imports.
"""
import csv
import io
import json
import re
import zipfile

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)

_ABBREV = (("st", "saint"), ("ste", "sainte"), ("ft", "fort"), ("mt", "mount"), ("pt", "port"))


def norm_city(name):
    """Normalise a city name so 'St. Louis', 'Saint Louis' and 'st louis' match."""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and "))
    words = s.split()
    if words and words[0] in dict(_ABBREV):
        words[0] = dict(_ABBREV)[words[0]]
    return " ".join(words)


def place_key(city, state):
    return f"{norm_city(city)}|{state.upper()}"


def read_fuel_csv(fileobj):
    """Parse the OPIS export; keep US rows and the cheapest row per truckstop ID."""
    best = {}
    skipped_non_us = 0
    for row in csv.DictReader(fileobj):
        state = row["State"].strip().upper()
        if state not in US_STATES:
            skipped_non_us += 1
            continue
        sid = int(row["OPIS Truckstop ID"])
        price = float(row["Retail Price"])
        if sid not in best or price < best[sid]["price"]:
            best[sid] = {
                "id": sid,
                "name": row["Truckstop Name"].strip(),
                "address": row["Address"].strip(),
                "city": row["City"].strip(),
                "state": state,
                "price": round(price, 5),
            }
    return list(best.values()), skipped_non_us


def parse_geonames_us(lines, wanted_keys, min_population=1000):
    """Return {place_key: [lat, lon]} from GeoNames US.txt lines.

    Keeps every populated place whose key is in `wanted_keys` (station cities)
    plus every place of at least `min_population` (so users can type them as
    start/finish). The most populous place wins when names collide in a state.
    """
    best = {}  # key -> (population, lat, lon)
    for line in lines:
        f = line.rstrip("\n").split("\t")
        if len(f) < 15 or f[6] != "P":
            continue
        state = f[10]
        pop = int(f[14] or 0)
        lat, lon = float(f[4]), float(f[5])
        for nm in {f[1], f[2]}:
            key = place_key(nm, state)
            if key in wanted_keys or pop >= min_population:
                if key not in best or pop > best[key][0]:
                    best[key] = (pop, lat, lon)
    return {k: [v[1], v[2]] for k, v in best.items()}


def geocode_stations(stations, places):
    located, missing = [], []
    for s in stations:
        pt = places.get(place_key(s["city"], s["state"]))
        if pt is None:
            missing.append(s)
        else:
            located.append({**s, "lat": pt[0], "lon": pt[1]})
    return located, missing


def open_geonames_zip(path_or_bytes):
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    zf = zipfile.ZipFile(src)
    return io.TextIOWrapper(zf.open("US.txt"), encoding="utf-8")


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))
