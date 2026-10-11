"""Turn user input ('Chicago, IL' or '41.88,-87.63') into coordinates, offline."""
import json
import re
from functools import lru_cache

from .build import place_key
from .errors import BadRequest, DataNotBuilt
from .geo import in_conus

STATE_NAMES = {
    "alabama": "AL", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL",
    "georgia": "GA", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
STATE_ABBRS = set(STATE_NAMES.values())
_COUNTRY_SUFFIXES = {"usa", "us", "u.s.", "u.s.a.", "united states", "united states of america"}

_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@lru_cache(maxsize=1)
def _load_places(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise DataNotBuilt(
            "places.json not found. Run `python manage.py build_stations` first."
        ) from exc


def _split_city_state(text):
    """Return (city, state_text) or None. Accepts 'Dallas, TX', 'Dallas, TX, USA'
    and 'Dallas TX' / 'Dallas Texas' (no comma)."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if parts and parts[-1].lower() in _COUNTRY_SUFFIXES:
        parts = parts[:-1]
    if len(parts) >= 2:
        return ", ".join(parts[:-1]), parts[-1]
    if len(parts) == 1:
        tokens = parts[0].split()
        for n in (2, 1):  # try two-word state names first ("New Mexico")
            if len(tokens) <= n:
                continue
            tail = " ".join(tokens[-n:]).lower().rstrip(".")
            if tail in STATE_NAMES or (n == 1 and tail.upper() in STATE_ABBRS):
                return " ".join(tokens[:-n]), tail
    return None


def resolve_location(text, places_path):
    """Return (lat, lon, label). Raises BadRequest for unusable input."""
    if not text or not text.strip():
        raise BadRequest("Location is required.")

    m = _LATLON.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not in_conus(lat, lon):
            raise BadRequest(f"{text!r} is outside the contiguous USA (use lat,lng order).")
        return lat, lon, f"{lat:.4f},{lon:.4f}"

    split = _split_city_state(text)
    if split is None:
        raise BadRequest(f"{text!r}: use 'City, ST' (e.g. 'Dallas, TX') or 'lat,lng'.")
    city, state = split
    state = state.strip().rstrip(".")
    state = STATE_NAMES.get(state.lower(), state.upper())

    places = _load_places(str(places_path))
    # GeoNames calls some cities "<name> City" (e.g. "New York City"); accept both forms.
    base = re.sub(r"\s+city$", "", city, flags=re.I)
    pt = None
    for candidate in (city, base, base + " city"):
        pt = places.get(place_key(candidate, state))
        if pt is not None:
            break
    if pt is None:
        raise BadRequest(f"Could not find {city!r}, {state} in the US gazetteer. Try 'lat,lng'.")
    if not in_conus(pt[0], pt[1]):
        raise BadRequest(f"{city}, {state} is outside the contiguous USA (Alaska and Hawaii are not supported).")
    return pt[0], pt[1], f"{city}, {state}"
