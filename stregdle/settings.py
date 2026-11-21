"""Django settings for Stregsystemdle.

The game owns no data of its own: it reads the stregsystem's tables over plain
SQL (see ``productdle/repository.py``), so ``DATABASES`` is deliberately empty
and no ORM models exist here.
"""

import os

import warnings

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Only used when STREGDLE_SECRET_KEY is unset. Nothing in this project signs
# anything (no sessions, no auth, no POST endpoints), so a public fallback is
# harmless; set a real key if that ever changes.
DEV_SECRET_KEY = "stregdle-dev-key-not-for-production-9f3c1a7e5b2d48c6e1"


def _env(name, default=""):
    return os.environ.get(name, default)


def _flag(name, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value not in ("0", "false", "False", "")


SECRET_KEY = _env("STREGDLE_SECRET_KEY", DEV_SECRET_KEY)

DEBUG = _flag("STREGDLE_DEBUG", False)

# Set STREGDLE_HTTPS=1 in production: the game sits behind a TLS-terminating
# reverse proxy there (which must send X-Forwarded-Proto). Off by default so
# local runs and the test client work over plain HTTP.
HTTPS = _flag("STREGDLE_HTTPS", False)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = HTTPS
SECURE_HSTS_SECONDS = int(_env("STREGDLE_HSTS_SECONDS", "31536000" if HTTPS else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
SECURE_HSTS_PRELOAD = HTTPS
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
X_FRAME_OPTIONS = "DENY"

if HTTPS and SECRET_KEY == DEV_SECRET_KEY:
    warnings.warn("Using the built-in development SECRET_KEY - set STREGDLE_SECRET_KEY in production.", stacklevel=1)

ALLOWED_HOSTS = [h for h in _env("STREGDLE_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# Where the "Menu"/"Genstart" buttons in the header point: the real stregsystem.
STREGSYSTEM_URL = _env("STREGSYSTEM_URL", "http://localhost:8000/")

# Link for "Se koden" in the footer. Hidden when unset.
SOURCE_URL = _env("STREGDLE_SOURCE_URL", "")

# Where the day's guesses are appended; empty disables the tally.
STREGDLE_STATS_DIR = _env("STREGDLE_STATS_DIR", str(BASE_DIR / "var"))

# Read-only access to the stregsystem database. Use a MySQL user that only has
# SELECT rights on the stregsystem schema.
STREG_DB = {
    "host": _env("STREG_DB_HOST", "127.0.0.1"),
    "port": int(_env("STREG_DB_PORT", "3306")),
    "user": _env("STREG_DB_USER", "stregdle"),
    "password": _env("STREG_DB_PASSWORD"),
    "database": _env("STREG_DB_NAME", "stregsystem"),
}

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "productdle",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "stregdle.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    },
]

WSGI_APPLICATION = "stregdle.wsgi.application"

# No database of our own - product data is read straight from the stregsystem.
DATABASES = {}

LANGUAGE_CODE = "da-dk"
TIME_ZONE = "Europe/Copenhagen"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"productdle": {"handlers": ["console"], "level": "INFO"}},
}
