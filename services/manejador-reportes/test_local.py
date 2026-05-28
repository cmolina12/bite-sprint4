#!/usr/bin/env python3
"""
test_local.py — Prueba el lado servidor del Experimento 2 SIN AWS ni Auth0 real.

Usa SQLite en memoria y mockea la validación del JWT, para verificar que:
  - acceso legítimo (tenant del token == tenant de la URL) → 200
  - acceso cross-tenant → 403
  - 20 ataques → 20/20 = 100%
  - los ataques quedan en AuditLog y /api/audit/ los reporta
  - tras los ataques, el acceso legítimo sigue en 200 (no hay bloqueo)
"""
import os
import sys

# Limpiar BD previa
if os.path.exists("/tmp/bite_localtest.sqlite3"):
    os.remove("/tmp/bite_localtest.sqlite3")

os.environ["DJANGO_SETTINGS_MODULE"] = "bite.settings_localtest"

import django
django.setup()

from django.core.management import call_command
call_command("migrate", run_syncdb=True, verbosity=0)

from reportes.models import Tenant, Report

# Semilla mínima
acme = Tenant.objects.create(name="Acme Corp", slug="acme-corp")
Tenant.objects.create(name="Globex Inc", slug="globex-inc")
Report.objects.create(tenant=acme, title="Costos abril", period="2026-04",
                      total_cost_usd=123.45)

# --- Mock de la validación de token DENTRO del middleware ---
import reportes.middleware.tenant_auth as mw


def fake_validate_token(token):
    # token de prueba con formato "tok:<tenant>:<sub>"
    _, tenant, sub = token.split(":")
    return {"sub": sub, "tenant": tenant}


def fake_extract_tenant_id(claims):
    return claims["tenant"]


mw.validate_token = fake_validate_token
mw.extract_tenant_id = fake_extract_tenant_id

from django.test import Client

c = Client()
TOKEN_A = "tok:acme-corp:auth0|userA"   # analista de acme-corp
USER_SUB = "auth0|userA"


def auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def check(name, cond):
    print(f"  [{'OK' if cond else 'FALLA'}] {name}")
    return cond


print("=" * 60)
print("TEST LOCAL — Experimento 2 (lado servidor)")
print("=" * 60)

results = []

# Paso 0 — sin token → 401
r = c.get("/api/reports/acme-corp/")
results.append(check(f"sin token → 401 (got {r.status_code})", r.status_code == 401))

# Paso 1 — acceso legítimo → 200
r = c.get("/api/reports/acme-corp/", **auth(TOKEN_A))
results.append(check(f"legítimo acme-corp → 200 (got {r.status_code})", r.status_code == 200))

# Paso 2 — cross-tenant → 403
r = c.get("/api/reports/globex-inc/", **auth(TOKEN_A))
results.append(check(f"cross-tenant globex-inc → 403 (got {r.status_code})", r.status_code == 403))

# Paso 3 — 20 ataques → 100%
codes = [c.get("/api/reports/globex-inc/", **auth(TOKEN_A)).status_code for _ in range(20)]
forbidden = sum(1 for x in codes if x == 403)
results.append(check(f"20 ataques → {forbidden}/20 = 403", forbidden == 20))

# Paso 4 — AuditLog vía /api/audit/
r = c.get("/api/audit/", {
    "outcome": "unauthorized_tenant",
    "user_sub": USER_SUB,
    "requested_tenant": "globex-inc",
})
data = r.json()
# 1 del paso 2 + 20 del paso 3 = 21 intentos cross-tenant registrados
results.append(check(
    f"/api/audit/ reporta los intentos (count={data.get('count')}, esperado >=21)",
    r.status_code == 200 and data.get("count", 0) >= 21,
))
if data.get("entries"):
    e = data["entries"][0]
    print(f"      muestra: {e['timestamp']} | {e['user_sub']} "
          f"({e['user_tenant_slug']}) → {e['method']} {e['path']} "
          f"({e['requested_tenant_slug']}) | {e['outcome']}")

# Paso 5 — acceso legítimo tras ataques → 200 (sin bloqueo)
r = c.get("/api/reports/acme-corp/", **auth(TOKEN_A))
results.append(check(f"legítimo tras ataques → 200 (got {r.status_code})", r.status_code == 200))

print("=" * 60)
ok = all(results)
print("RESULTADO:", "TODO OK ✓" if ok else "HAY FALLAS ✗")
sys.exit(0 if ok else 1)
