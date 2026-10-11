"""Small geometry helpers. Pure Python, no Django imports."""
import math

EARTH_RADIUS_MI = 3958.7613
MI_PER_DEG_LAT = 69.093


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def approx_dist_mi(lat1, lon1, lat2, lon2):
    """Equirectangular approximation. Plenty accurate at corridor scale (<50 mi)
    and several times faster than haversine, which matters in the hot loop."""
    mean_lat = math.radians((lat1 + lat2) / 2)
    dx = (lon2 - lon1) * math.cos(mean_lat) * MI_PER_DEG_LAT
    dy = (lat2 - lat1) * MI_PER_DEG_LAT
    return math.hypot(dx, dy)


def decode_polyline(encoded, precision=5):
    """Decode a Google/OSRM encoded polyline into [(lat, lon), ...]."""
    factor = 10 ** precision
    index = lat = lon = 0
    coords = []
    n = len(encoded)
    while index < n:
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def cumulative_miles(points):
    """Running distance along the polyline; first element is 0.0."""
    out = [0.0]
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        out.append(out[-1] + haversine_mi(la1, lo1, la2, lo2))
    return out


# Rough bounding box of the contiguous USA. It is only a sanity check for raw
# "lat,lng" input (it also admits slivers of Canada/Mexico and nearby ocean).
CONUS_BOUNDS = (24.4, 49.5, -125.0, -66.9)  # lat_min, lat_max, lon_min, lon_max


def in_conus(lat, lon):
    la0, la1, lo0, lo1 = CONUS_BOUNDS
    return la0 <= lat <= la1 and lo0 <= lon <= lo1
