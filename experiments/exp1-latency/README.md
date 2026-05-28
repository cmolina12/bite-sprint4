# Experimento 1 — Latencia (ASR-LAT-01)

Valida **CQRS + Vista Materializada**: compara el P95 de una agregación en vivo
sobre +10M registros crudos (baseline) contra la lectura de una vista
materializada pre-agregada.

- **Umbral (ASR-LAT-01):** P95 ≤ 500 ms con vista materializada.
- **Baseline esperado:** P95 > 2000 ms (agregación en tiempo real inviable).

## Componentes

| Pieza | Ubicación |
|---|---|
| Microservicio Reportes (Nest.js, lado Query del CQRS) | `services/manejador-reportes-nest/` |
| Endpoint baseline | `GET /api/reports/:tenant/baseline` |
| Endpoint materializado | `GET /api/reports/:tenant/materialized` |
| Seed de +10M docs | `services/manejador-reportes-nest/scripts/seed-costos.js` |
| Construir vista materializada | `services/manejador-reportes-nest/scripts/materialize.js` |
| Plan de carga | `experiments/exp1-latency/BITE-Exp1-Latencia.jmx` |

> Los dos endpoints aceptan `?light=1` para devolver solo conteo + tiempo (sin
> las filas), de modo que JMeter mida la latencia del query y no la transferencia
> del payload.

## Paso a paso

### 1. MongoDB y el servicio Reportes ya están desplegados por Terraform

Tras `terraform apply` (FASE 1 del RUNBOOK), ya tienes corriendo:
- EC2 con MongoDB en Docker (`mongo_public_ip` / `mongo_private_ip`)
- EC2 con el microservicio Reportes-Nest en Docker (`reports_nest_url`)

No tienes que levantarlos a mano. Los pasos de abajo (seed, materialize, JMeter)
se corren contra esa infra ya desplegada. Si prefieres montarlo manualmente
(sin Terraform), las instrucciones manuales quedan al final como referencia.

### 2. Sembrar la colección cruda (+10M docs)

El seed se corre **desde dentro de la red de AWS** (la EC2 de Mongo solo acepta
27017 desde Reportes-Nest, no desde tu IP). Lo más simple es correrlo en la
propia EC2 de MongoDB vía SSH:

```bash
ssh -i <vockey.pem> ubuntu@<mongo_public_ip>     # ver output mongo_ssh

# dentro de la EC2 de Mongo:
sudo apt-get update -y && sudo apt-get install -y nodejs npm git
git clone <tu-repo-sprint4> bite && cd bite/services/manejador-reportes-nest
npm install
MONGO_URI="mongodb://localhost:27017" node scripts/seed-costos.js
# tarda varios minutos; inserta 10.5M docs por defecto
```

### 3. Prueba BASELINE (sin vista materializada)

Usa la URL del output `exp1_baseline_url`. Abrir `BITE-Exp1-Latencia.jmx` en
JMeter, **deshabilitar** el Thread Group "2 - Materializado", y correr solo
"1 - Baseline". O por consola (apuntando directo al Nest en :3000):

```bash
jmeter -n -t BITE-Exp1-Latencia.jmx \
  -Jhost=<reports_nest_public_ip> -Jport=3000 -Jtenant=acme-corp -Jusers=50 -Jloops=20 \
  -l baseline.jtl -e -o reporte-baseline/
```

Anota el **P95** del Aggregate Report (esperado > 2000 ms).

### 4. Construir la vista materializada (una sola vez)

```bash
# en la EC2 de Mongo (o donde tengas acceso a 27017):
cd bite/services/manejador-reportes-nest
MONGO_URI="mongodb://localhost:27017" node scripts/materialize.js
```

### 5. Prueba MATERIALIZADO

Mismo plan, ahora solo el Thread Group "2 - Materializado":

```bash
jmeter -n -t BITE-Exp1-Latencia.jmx \
  -Jhost=<reports_nest_public_ip> -Jport=3000 -Jtenant=acme-corp -Jusers=50 -Jloops=20 \
  -l materialized.jtl -e -o reporte-materializado/
```

Anota el **P95** (esperado ≤ 500 ms).

### 6. Repetir 3 veces y comparar

Repetir pasos 3 y 5 tres veces. La variación entre corridas debe ser < 10%.
Contrastar los P95 de ambos escenarios → con vista materializada debe cumplir
el umbral de 500 ms.

## Criterio de validación

| Resultado | Condición | Acción |
|---|---|---|
| ✅ Válida | P95 materializado ≤ 500 ms en las 3 repeticiones | Táctica confirmada |
| ❌ Inválida | P95 materializado > 500 ms | Revisar pre-agregación, índices de MongoDB y la vista |

## Nota de pruebas locales

La lógica del pipeline de agregación se validó con
`scripts/verify-pipeline.js` (réplica en JS puro del `$group`/`$project`, sin
MongoDB). La prueba end-to-end con volumen real se hace en AWS según los pasos
de arriba.
