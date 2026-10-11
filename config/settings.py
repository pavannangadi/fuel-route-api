import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = ["routing"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]

# No database: station data is a static JSON file loaded once into memory.
DATABASES = {}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Fuel routing ---
DATA_DIR = BASE_DIR / "data"
FUEL_CSV_PATH = DATA_DIR / "fuel-prices-for-be-assessment.csv"
STATIONS_PATH = DATA_DIR / "stations.json"
PLACES_PATH = DATA_DIR / "places.json"

VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
CORRIDOR_MILES = 10  # how far off the route a station may be and still count

OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
ROUTING_TIMEOUT = 15
PLAN_CACHE_SECONDS = 60 * 60
