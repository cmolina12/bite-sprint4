#!/usr/bin/env python3
"""
Experimento 2 — Seguridad (Sprint 4) — Access Token + Validación por Tenant
ASR-SEG-01: detección del 100% de accesos cross-tenant.

Hipótesis:
   "Si valido el claim tenant_id del JWT en cada microservicio, el 100% de los
    intentos cross-tenant serán detectados y rechazados con HTTP 403, sin afectar
    los accesos legítimos de cada tenant."

Alcance Sprint 4: SOLO detección + auditoría (sin bloqueo de cuenta ni email,
que eran SEG-02). Por eso el paso 5 verifica que los accesos legítimos siguen
funcionando DESPUÉS de los ataques.

Pasos:
    1. Acceso legítimo: Tenant A → recursos de Tenant A → 200
    2. Acceso cruzado: Tenant A → recursos de Tenant B → 403
    3. Repetir el ataque 20 veces → 100% de detección (403)
    4. Verificar en AuditLog (/api/audit/) que los 20 quedaron registrados
       con timestamp, usuario y recurso solicitado
    5. Acceso legítimo de nuevo tras los ataques → 200 (0% de falsos positivos)

Pre-requisitos:
    - Microservicio Reportes desplegado con el TenantAuthorizationMiddleware
    - Auth0 con dos usuarios y la Post-Login Action que inyecta tenant_id:
        * analyst-acme@example.com   → tenant_id: acme-corp
        * analyst-globex@example.com → tenant_id: globex-inc

Variables de entorno requeridas:
    KONG_URL              — http://<elastic-ip>:8000
    AUTH0_DOMAIN          — dev-xxxxx.us.auth0.com
    AUTH0_CLIENT_ID       — del Auth0 Application (Regular Web App)
    AUTH0_CLIENT_SECRET   — del Auth0 Application
    AUTH0_AUDIENCE        — https://bite.co/api
    TENANT_A_USERNAME     — email del analista de acme-corp
    TENANT_A_PASSWORD     — password del usuario
"""

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# =============================================================================
# Config
# =============================================================================
KONG_URL = os.environ.get("KONG_URL", "").rstrip("/")
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://bite.co/api")

TENANT_A_USER = os.environ.get("TENANT_A_USERNAME", "")
TENANT_A_PASS = os.environ.get("TENANT_A_PASSWORD", "")

TENANT_A_SLUG = os.environ.get("TENANT_A_SLUG", "acme-corp")
TENANT_B_SLUG = os.environ.get("TENANT_B_SLUG", "globex-inc")
N_ATTACKS = int(os.environ.get("N_ATTACKS", "20"))

required = {
    "KONG_URL": KONG_URL,
    "AUTH0_DOMAIN": AUTH0_DOMAIN,
    "AUTH0_CLIENT_ID": AUTH0_CLIENT_ID,
    "AUTH0_CLIENT_SECRET": AUTH0_CLIENT_SECRET,
    "TENANT_A_USERNAME": TENANT_A_USER,
    "TENANT_A_PASSWORD": TENANT_A_PASS,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"ERROR: faltan variables de entorno: {', '.join(missing)}")
    sys.exit(1)


# =============================================================================
# Helpers
# =============================================================================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def banner(msg):
    print("\n" + "=" * 64)
    print(msg)
    print("=" * 64)


def get_token(username, password):
    """Obtiene un access_token de Auth0 vía Resource Owner Password Grant."""
    resp = requests.post(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        json={
            "grant_type": "password",
            "username": username,
            "password": password,
            "audience": AUTH0_AUDIENCE,
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "scope": "openid profile email",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        log(f"Error obteniendo token para {username}: {resp.status_code} {resp.text}")
        return None
    return resp.json()["access_token"]


def decode_sub(token):
    """Lee el claim 'sub' del JWT sin validar firma (solo para filtrar AuditLog)."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub")
    except Exception:
        return None


def request_reports(token, tenant_slug):
    """GET a /api/reports/<tenant_slug>/ con el token."""
    return requests.get(
        f"{KONG_URL}/api/reports/{tenant_slug}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


def query_audit(**filters):
    """GET a /api/audit/ con filtros por query string."""
    return requests.get(f"{KONG_URL}/api/audit/", params=filters, timeout=10)


# =============================================================================
# Paso 1 — Acceso legítimo
# =============================================================================
banner("PASO 1: Acceso legítimo")
log(f"Obteniendo token del analista del Tenant A ({TENANT_A_SLUG})...")
token_a = get_token(TENANT_A_USER, TENANT_A_PASS)
if not token_a:
    sys.exit(1)
user_sub = decode_sub(token_a)
log(f"Token A obtenido ({len(token_a)} chars), sub={user_sub}")

log(f"Probando acceso legítimo: Tenant A → {TENANT_A_SLUG}/")
resp = request_reports(token_a, TENANT_A_SLUG)
log(f"  Resultado: HTTP {resp.status_code}")
step1_ok = resp.status_code == 200
log("  ✓ Acceso legítimo PERMITIDO" if step1_ok
    else f"  ✗ FALLO: esperaba 200, body: {resp.text[:200]}")


# =============================================================================
# Paso 2 — Intento de acceso entre tenants
# =============================================================================
banner("PASO 2: Acceso entre tenants (Tenant A → recursos de Tenant B)")
log(f"Atacante: Tenant A intentando acceder a {TENANT_B_SLUG}")
resp = request_reports(token_a, TENANT_B_SLUG)
log(f"  Resultado: HTTP {resp.status_code}")
step2_ok = resp.status_code == 403
log("  ✓ Acceso DENEGADO (ASR-SEG-01)" if step2_ok
    else f"  ✗ FALLO: esperaba 403, retornó {resp.status_code} — {resp.text[:200]}")


# =============================================================================
# Paso 3 — Repetir N veces para verificar 100% de detección
# =============================================================================
banner(f"PASO 3: Repetir ataque {N_ATTACKS} veces (validar 100% de detección)")
# Marca de tiempo para aislar SOLO los ataques de esta fase en el AuditLog
attack_phase_start = datetime.now(timezone.utc).isoformat()
results = []
for _ in range(N_ATTACKS):
    r = request_reports(token_a, TENANT_B_SLUG)
    results.append(r.status_code)

forbidden = sum(1 for r in results if r == 403)
detection_rate = forbidden / N_ATTACKS * 100
log(f"  HTTP 403: {forbidden}/{N_ATTACKS} ({detection_rate:.0f}%)")
step3_ok = forbidden == N_ATTACKS
log(f"  ✓ ASR-SEG-01 cumplido: 100% de intentos detectados" if step3_ok
    else f"  ✗ ASR-SEG-01 NO cumplido: solo {forbidden}/{N_ATTACKS} detectados")


# =============================================================================
# Paso 4 — Verificar que los N ataques quedaron en AuditLog
# =============================================================================
banner("PASO 4: Verificar trazabilidad en AuditLog")
log("Consultando /api/audit/ ...")
resp = query_audit(
    outcome="unauthorized_tenant",
    user_sub=user_sub,
    requested_tenant=TENANT_B_SLUG,
    since=attack_phase_start,
    limit=N_ATTACKS,
)
step4_ok = False
if resp.status_code == 200:
    data = resp.json()
    logged = data.get("count", 0)
    log(f"  Entradas registradas en esta fase: {logged}/{N_ATTACKS}")
    step4_ok = logged >= N_ATTACKS
    sample = data.get("entries", [])
    if sample:
        e = sample[0]
        log("  Muestra de una entrada:")
        log(f"    timestamp={e['timestamp']}")
        log(f"    usuario  ={e['user_sub']} (tenant {e['user_tenant_slug']})")
        log(f"    recurso  ={e['method']} {e['path']} (tenant {e['requested_tenant_slug']})")
    log("  ✓ Trazabilidad completa: 100% de los intentos registrados" if step4_ok
        else f"  ✗ Solo {logged}/{N_ATTACKS} registrados en AuditLog")
else:
    log(f"  ✗ /api/audit/ retornó HTTP {resp.status_code}: {resp.text[:200]}")


# =============================================================================
# Paso 5 — Acceso legítimo DESPUÉS de los ataques (0% de falsos positivos)
# =============================================================================
banner("PASO 5: Acceso legítimo tras los ataques (sin falsos positivos)")
log(f"Re-obteniendo token del Tenant A (debe seguir funcionando, no hay bloqueo)...")
token_a2 = get_token(TENANT_A_USER, TENANT_A_PASS)
step5_ok = False
if token_a2:
    resp = request_reports(token_a2, TENANT_A_SLUG)
    log(f"  Acceso legítimo Tenant A → {TENANT_A_SLUG}/: HTTP {resp.status_code}")
    step5_ok = resp.status_code == 200
    log("  ✓ El acceso legítimo NO se ve afectado (0% impacto)" if step5_ok
        else f"  ✗ FALLO: el acceso legítimo fue afectado ({resp.status_code})")
else:
    log("  ✗ No se pudo obtener token — ¿el usuario quedó bloqueado? "
        "(en Sprint 4 NO debería bloquearse)")


# =============================================================================
# Resumen
# =============================================================================
banner("RESUMEN — Experimento 2 (ASR-SEG-01)")
checks = [
    ("Paso 1 — acceso legítimo (200)", step1_ok),
    ("Paso 2 — cross-tenant denegado (403)", step2_ok),
    (f"Paso 3 — {N_ATTACKS}/{N_ATTACKS} detección (100%)", step3_ok),
    ("Paso 4 — trazabilidad en AuditLog", step4_ok),
    ("Paso 5 — sin impacto en acceso legítimo", step5_ok),
]
for name, ok in checks:
    print(f"  [{'OK' if ok else 'FALLA'}] {name}")

all_ok = all(ok for _, ok in checks)
print()
print("  ASR-SEG-01: " + ("VÁLIDA — táctica confirmada" if all_ok
                          else "INVÁLIDA — revisar middleware/config"))
sys.exit(0 if all_ok else 1)
