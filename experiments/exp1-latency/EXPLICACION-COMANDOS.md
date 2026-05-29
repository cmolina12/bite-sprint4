# Explicación de Comandos — Experimento 1 (Latencia)

Qué hace **cada comando** que ejecutas durante el experimento, explicado línea
por línea. Útil para entenderlo a fondo y para narrar el video con propiedad.

---

## 1. Despliegue (CloudShell)

### `cd ~/bite-sprint4/terraform`
Entra a la carpeta donde están los archivos `.tf` (la definición de la
infraestructura). Terraform opera sobre el directorio actual.

### `terraform init`
Inicializa el proyecto: lee los `.tf`, detecta que usas el proveedor de AWS y
descarga el plugin correspondiente a la carpeta `.terraform/`. Se corre una vez
por proyecto (o cuando cambian los proveedores).

### `terraform apply`
Compara lo que está definido en los `.tf` con lo que existe en AWS, calcula las
diferencias y crea/modifica los recursos para que coincidan. Pide confirmación
(`yes`) y luego provisiona: VPC, subredes, security groups, las EC2 (MongoDB y
Reportes-Nest), RDS, Kong, el balanceador, etc.

### `terraform output`
Imprime los valores de salida definidos en `outputs.tf`: IPs públicas, URLs de
los endpoints, etc. Es de dónde sacas las direcciones para los siguientes pasos.

---

## 2. Carga de datos (EC2 de MongoDB)

### `git clone https://github.com/cmolina12/bite-sprint4.git ~/bite-sprint4`
Descarga el código del repositorio dentro de la instancia, para tener los
scripts de seed y materialización. (Si ya existe, se usa `git pull` para
actualizar.)

### `cd ~/bite-sprint4/services/manejador-reportes-nest`
Entra a la carpeta del microservicio Reportes, donde viven los scripts en
`scripts/`.

### `npm install`
Instala las dependencias de Node declaradas en `package.json`. La que importa
para el seed es el driver `mongodb`, que permite conectarse a la base desde
Node.

### `SINGLE_TENANT=acme-corp MONGO_URI="mongodb://localhost:27017" node scripts/seed-costos.js`
Ejecuta el script de siembra. Desglose:
- `SINGLE_TENANT=acme-corp` → variable de entorno que fuerza que TODOS los
  documentos se asignen al tenant `acme-corp`. Sin ella, el script repartiría
  los documentos entre 5 tenants. Lo forzamos a uno solo porque el ASR exige que
  **un reporte** (que filtra por un tenant) agregue +10M registros.
- `MONGO_URI="mongodb://localhost:27017"` → dónde está MongoDB. Como el script
  corre en la misma EC2 que la base, usamos `localhost`.
- `node scripts/seed-costos.js` → corre el script. Inserta 10.5M documentos en
  lotes de 50.000, y al final crea un índice por `(tenant_id, date)`.

### `MONGO_URI="mongodb://localhost:27017" node scripts/materialize.js`
Construye la vista materializada. El script corre una agregación sobre la
colección cruda `costos` que:
1. Agrupa los documentos por tenant, proveedor, servicio, año y mes.
2. Suma el costo y el uso de cada grupo, y cuenta los registros.
3. Con `$merge`, **escribe** ese resultado en la colección `reportes_agregados`.
El resultado: los 10.5M documentos crudos quedan resumidos en 336 documentos
pre-agregados. Esta operación pesada se paga UNA vez aquí, no en cada consulta.

---

## 3. Prueba de los endpoints (CloudShell o Mac)

### `curl -s "http://<IP_NEST>:3000/api/reports/acme-corp/materialized?light=1"`
Hace una petición HTTP GET al endpoint materializado:
- `curl` → cliente HTTP de línea de comandos.
- `-s` → modo silencioso (no muestra la barra de progreso).
- La ruta `/api/reports/acme-corp/materialized` → pide el reporte del tenant
  `acme-corp` leyendo la vista materializada.
- `?light=1` → parámetro que le dice al endpoint que devuelva solo el resumen
  (conteo y tiempo de query), sin las filas, para no transferir un payload
  grande que ensucie la medición.
Responde en milisegundos porque solo lee 336 documentos ya calculados.

### `curl -s -m 40 "http://<IP_NEST>:3000/api/reports/acme-corp/baseline?light=1"`
Igual que el anterior, pero contra el endpoint baseline:
- `-m 40` → timeout de cliente de 40 segundos (corta el curl si no responde).
- `/baseline` → este endpoint corre la agregación EN VIVO sobre los 10.5M
  documentos crudos, sin vista materializada.
El servidor tiene su propio límite (`BASELINE_MAX_MS=30000`, 30s); al excederlo,
MongoDB corta la operación y el endpoint responde con un estado `TIMEOUT`. Es el
resultado esperado: agregar en vivo sobre +10M es inviable.

---

## 4. Prueba de carga (JMeter, en el Mac)

JMeter no es comando de terminal; se opera por interfaz. Conceptualmente:
- **Thread Group "Baseline"** → simula N usuarios concurrentes pegando al
  endpoint baseline. Todos dan timeout → 100% de error.
- **Thread Group "Materializado"** → simula N usuarios concurrentes pegando al
  endpoint materializado. Miden el tiempo de respuesta de cada uno.
- **Aggregate Report** → tabla que resume las métricas. La columna **95% Line**
  es el P95: el tiempo bajo el cual responde el 95% de las solicitudes. Ese es el
  número que el ASR-LAT-01 exige que sea ≤ 500 ms.

---

## 5. Limpieza (CloudShell)

### `terraform destroy`
Elimina TODOS los recursos que `apply` creó en AWS, para no seguir consumiendo
créditos. Pide confirmación (`yes`). Borra también los datos de MongoDB, así que
al volver hay que sembrar de nuevo.

---

## ¿Por qué este experimento prueba el ASR?

El ASR-LAT-01 dice: "un reporte que agrega +10M registros debe tener P95 ≤ 500
ms". El experimento compara las dos únicas formas de servir ese reporte:

- **Sin la táctica (baseline):** recalcular en cada consulta → 100% timeout.
- **Con la táctica (CQRS + vista materializada):** leer lo pre-calculado →
  P95 = 271 ms.

La diferencia entre ambos es exactamente el valor que aporta la decisión
arquitectónica. Por eso el baseline "fallando" no es un error del experimento:
es la evidencia de que la táctica era necesaria.
