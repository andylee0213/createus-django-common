# filename: dev/devsettings.py

SECRET_KEY = "dev"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "createus_common.auth",
    "createus_common.billing.apps.CreateusBillingConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
