"""
Settings SOLO para el test local (no se despliega).
Sobreescribe Postgres→SQLite y Redis→locmem, y activa Auth0 (modo no permisivo)
para que el TenantAuthorizationMiddleware valide de verdad.
"""
import os

os.environ.setdefault("AUTH0_DOMAIN", "dev-localtest.us.auth0.com")

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/bite_localtest.sqlite3",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
