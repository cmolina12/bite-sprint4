# BITE.co — Sprint 4: Runbook de Experimentos

Guía paso a paso para probar y ejecutar los dos experimentos del Sprint 4.

- **Experimento 1 — Latencia:** CQRS + vista materializada (ASR-LAT-01, P95 ≤ 500 ms)
- **Experimento 2 — Seguridad:** Access Token + validación por tenant (ASR-SEG-01, 100% detección)

> **Estado actual**
> - Exp 2 (Seguridad): **completo y probado localmente.** Listo para desplegar.
> - Exp 1 (Latencia): **completo.** Microservicio Reportes en Nest.js con los
>   endpoints baseline/materializado, scripts de seed y materialización en Node,
>   y plan de JMeter. Lógica de agregación validada localmente; la prueba con
>   volumen real (+10M docs) se corre en AWS.

---

## FASE 0 — Probar el Exp 2 en local (sin AWS, sin Auth0)

Esto valida el lado servidor (middleware + endpoint de auditoría) antes de gastar
nada en AWS. Usa SQLite y mockea Auth0.

```bash
cd services/manejador-reportes
pip install "Django==5.2.5" requests --break-system-packages
python3 test_local.py
```

Salida esperada — los 6 checks en OK:

```
[OK] sin token → 401
[OK] legítimo acme-corp → 200
[OK] cross-tenant globex-inc → 403
[OK] 20 ataques → 20/20 = 403
[OK] /api/audit/ reporta los intentos (count=21)
[OK] legítimo tras ataques → 200
RESULTADO: TODO OK ✓
```

> Las líneas `WARNING ... UNAUTHORIZED TENANT ACCESS` son el log normal del
> middleware al detectar cada ataque. No son errores.

Si esto pasa, el código de seguridad está bien y el resto es solo desplegarlo.

---

## FASE 1 — Desplegar la infraestructura en AWS

> Igual que en el Sprint 3 — el Terraform y el bootstrap ya existen. Desde
> CloudShell o tu máquina con las credenciales de AWS Academy:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# editar terraform.tfvars con tus valores (ver más abajo)
terraform init
terraform apply
```

Variables clave en `terraform.tfvars` (revisar el `.example`):
- credenciales/labRole de AWS Academy
- `auth0_domain`, `auth0_audience`
- (para Exp 1, cuando lo agreguemos: tamaño de disco de la EC2 de MongoDB → 30 GB)

Al terminar, `terraform output` te da las IPs (Kong/Elastic IP).

---

## FASE 2 — Configurar Auth0 (solo Exp 2)

Necesitas, igual que en Sprint 3:

1. **Una API** en Auth0 con identifier `https://bite.co/api`.
2. **Una Application** (Regular Web App) — de ahí salen `client_id` y `client_secret`.
   Habilitar el grant **Password** (Authentication → Database → Password) para el
   Resource Owner Password Grant que usa el script.
3. **Post-Login Action** que inyecta el claim `tenant_id` en el access token.
   El namespace del claim debe coincidir con `AUTH0_TENANT_CLAIM` de Django.
4. **Dos usuarios de prueba** con `app_metadata.tenant_id`:
   - `analyst-acme@example.com`   → `tenant_id: acme-corp`
   - `analyst-globex@example.com` → `tenant_id: globex-inc`

> Si ya tienes el tenant de Auth0 del Sprint 3 configurado, reutilízalo tal cual —
> no cambió nada del lado de Auth0.

Los slugs `acme-corp` y `globex-inc` deben existir como `Tenant` en la BD (los
crea el seed del servicio, igual que en Sprint 3).

---

## FASE 3 — Ejecutar el Experimento 2 (Seguridad)

### Opción A — Script de Python (recomendado para evidencia)

```bash
cd experiments/exp2-security

export KONG_URL="http://<elastic-ip>:8000"
export AUTH0_DOMAIN="dev-xxxxx.us.auth0.com"
export AUTH0_CLIENT_ID="..."
export AUTH0_CLIENT_SECRET="..."
export AUTH0_AUDIENCE="https://bite.co/api"
export TENANT_A_USERNAME="analyst-acme@example.com"
export TENANT_A_PASSWORD="..."

python3 run-experiment-2.py
```

Salida esperada (resumen final):

```
RESUMEN — Experimento 2 (ASR-SEG-01)
  [OK] Paso 1 — acceso legítimo (200)
  [OK] Paso 2 — cross-tenant denegado (403)
  [OK] Paso 3 — 20/20 detección (100%)
  [OK] Paso 4 — trazabilidad en AuditLog
  [OK] Paso 5 — sin impacto en acceso legítimo
  ASR-SEG-01: VÁLIDA — táctica confirmada
```

### Opción B — Postman

1. Importar `BITE-Exp2-Seguridad.postman_collection.json`.
2. En la colección → Variables, llenar: `kong_url`, `auth0_client_id`,
   `auth0_client_secret`, `tenant_a_pass` (los demás ya traen default).
3. Ejecutar los requests en orden 1 → 2.
4. Para el paso 3 (20 ataques): abrir el **Collection Runner**, seleccionar solo
   "3. Ataque cross-tenant", poner **20 iteraciones**, correr. Deben dar 20/20 = 403.
5. Ejecutar "4. Verificar AuditLog" → en la consola verás `count` de intentos
   registrados y una muestra.
6. Ejecutar "5. Acceso legítimo tras ataques" → debe dar 200.

> Las dos opciones validan lo mismo. El script te da el dictamen automático;
> Postman es bueno para mostrar request por request en la sustentación.

---

## FASE 4 — Experimento 1 (Latencia)

El microservicio Reportes (Nest.js) y todo el experimento están en:
- Servicio: `services/manejador-reportes-nest/`
- Experimento (JMeter + guía detallada): `experiments/exp1-latency/`

Resumen del flujo (el paso a paso completo está en
`experiments/exp1-latency/README.md`):

1. Levantar EC2 con MongoDB en Docker (disco 30 GB).
2. Desplegar el servicio Reportes (Nest.js) apuntando a esa MongoDB.
3. `node scripts/seed-costos.js` → siembra +10M docs en la colección cruda.
4. JMeter contra `/api/reports/<tenant>/baseline` → P95 (esperado > 2000 ms).
5. `node scripts/materialize.js` → construye la vista materializada (una vez).
6. JMeter contra `/api/reports/<tenant>/materialized` → P95 (esperado ≤ 500 ms).
7. Repetir 3 veces, comparar; variación < 10% entre corridas.

> **Nota de stack:** el Exp 1 está en Nest.js + MongoDB, coherente con el
> documento de tecnologías (Reportes = Nest.js, lado Query del CQRS). El Exp 2
> reutiliza el servicio Django del Sprint 3 (manejador-reportes). Son dos
> servicios distintos a propósito.

---

## Apéndice — Qué cambió respecto al Sprint 3

| Archivo | Cambio |
|---|---|
| `reportes/middleware/tenant_auth.py` | Se quitó el disparo de bloqueo+email (SEG-02). Solo detección + AuditLog. |
| `reportes/views_api.py` | Nuevo endpoint de solo lectura `/api/audit/`. |
| `reportes/urls_api.py` | Ruta `audit/`. |
| `experiments/exp2-security/run-experiment-2.py` | Reescrito a 5 pasos (incluye verificación de AuditLog y acceso legítimo post-ataque). |
| `experiments/exp2-security/BITE-Exp2-Seguridad.postman_collection.json` | Nuevo — colección Postman equivalente. |
| `services/manejador-reportes/test_local.py` | Nuevo — prueba local con SQLite (no se despliega). |
| `services/manejador-reportes/bite/settings_localtest.py` | Nuevo — settings de prueba local (no se despliega). |
| `services/manejador-reportes-nest/` | Nuevo — microservicio Reportes en Nest.js (Exp 1, lado Query del CQRS). |
| `experiments/exp1-latency/BITE-Exp1-Latencia.jmx` | Nuevo — plan JMeter baseline vs materializado. |
| `experiments/exp1-latency/README.md` | Nuevo — guía paso a paso del Exp 1. |

`reportes/security_response.py` queda en el repo pero **ya no se usa** en Sprint 4
(era la lógica de SEG-02).
