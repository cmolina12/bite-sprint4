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

### 1. Levantar MongoDB (EC2 con Docker)

```bash
docker run -d --name mongo -p 27017:27017 -v mongodata:/data/db mongo:7
```

> Disco: pide a la EC2 un volumen de ~30 GB. Los 10M+ docs ocupan varios GB y
> el `$merge` necesita espacio temporal.

### 2. Desplegar el microservicio Reportes

```bash
cd services/manejador-reportes-nest
npm install
npm run build
export MONGO_URI="mongodb://<mongo-host>:27017"
export MONGO_DB="bite"
npm start          # escucha en :3000 (o detrás de Kong en :8000)
```

(o vía Docker: `docker build -t bite-reportes . && docker run -p 3000:3000 -e MONGO_URI=... bite-reportes`)

### 3. Sembrar la colección cruda

```bash
cd services/manejador-reportes-nest
MONGO_URI="mongodb://<mongo-host>:27017" node scripts/seed-costos.js
# tarda varios minutos; inserta 10.5M docs por defecto
```

### 4. Prueba BASELINE (sin vista materializada)

Abrir `BITE-Exp1-Latencia.jmx` en JMeter, **deshabilitar** el Thread Group
"2 - Materializado", y correr solo "1 - Baseline". O por consola:

```bash
jmeter -n -t BITE-Exp1-Latencia.jmx \
  -Jhost=<elastic-ip> -Jport=8000 -Jtenant=acme-corp -Jusers=50 -Jloops=20 \
  -l baseline.jtl -e -o reporte-baseline/
```

Anota el **P95** del Aggregate Report (esperado > 2000 ms).

### 5. Construir la vista materializada (una sola vez)

```bash
cd services/manejador-reportes-nest
MONGO_URI="mongodb://<mongo-host>:27017" node scripts/materialize.js
```

### 6. Prueba MATERIALIZADO

Mismo plan, ahora solo el Thread Group "2 - Materializado":

```bash
jmeter -n -t BITE-Exp1-Latencia.jmx \
  -Jhost=<elastic-ip> -Jport=8000 -Jtenant=acme-corp -Jusers=50 -Jloops=20 \
  -l materialized.jtl -e -o reporte-materializado/
```

Anota el **P95** (esperado ≤ 500 ms).

### 7. Repetir 3 veces y comparar

Repetir pasos 4 y 6 tres veces. La variación entre corridas debe ser < 10%.
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
