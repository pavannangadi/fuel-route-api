from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from routing import build

GEONAMES_URL = "https://download.geonames.org/export/dump/US.zip"


class Command(BaseCommand):
    help = "Geocode the fuel price CSV (city centroids via GeoNames) into data/stations.json + data/places.json."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(settings.FUEL_CSV_PATH))
        parser.add_argument("--geonames-zip", help="Path to a local GeoNames US.zip (skips the download).")

    def handle(self, *args, **opts):
        csv_path = Path(opts["csv"])
        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")

        with open(csv_path, newline="", encoding="utf-8") as fh:
            stations, non_us = build.read_fuel_csv(fh)
        self.stdout.write(f"{len(stations)} unique US stations ({non_us} non-US rows skipped)")

        if opts["geonames_zip"]:
            source = open(opts["geonames_zip"], "rb")
        else:
            self.stdout.write(f"Downloading {GEONAMES_URL} ...")
            resp = requests.get(GEONAMES_URL, timeout=120)
            resp.raise_for_status()
            source = resp.content
        wanted = {build.place_key(s["city"], s["state"]) for s in stations}
        with build.open_geonames_zip(source) as lines:
            places = build.parse_geonames_us(lines, wanted)

        located, missing = build.geocode_stations(stations, places)
        self.stdout.write(f"Located {len(located)}/{len(stations)} stations; {len(missing)} unmatched")
        for s in missing[:15]:
            self.stdout.write(f"  unmatched: {s['name']} - {s['city']}, {s['state']}")

        settings.DATA_DIR.mkdir(exist_ok=True)
        build.write_json(settings.STATIONS_PATH, located)
        build.write_json(settings.PLACES_PATH, places)
        self.stdout.write(self.style.SUCCESS(f"Wrote {settings.STATIONS_PATH} and {settings.PLACES_PATH}"))
