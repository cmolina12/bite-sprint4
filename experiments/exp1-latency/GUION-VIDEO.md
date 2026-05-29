# Guion de Video — Experimento 1: Latencia (ASR-LAT-01)
### BITE.co Sprint 4 · CQRS + Vista Materializada

> Cómo usar este documento: la columna **HACER** es lo que ejecutas en pantalla.
> La columna **DECIR** es lo que narras. No tienes que leerlo literal — es una guía.
> Tiempo estimado de grabación: 8–12 min (el seed de datos es lo más largo).

---

## ANTES DE GRABAR (preparación, no se graba)

1. Ten abiertas y listas:
   - CloudShell (para Terraform)
   - La consola de EC2 (para conectarte a las instancias)
   - JMeter en tu Mac, con el plan `BITE-Exp1-Latencia.jmx` ya abierto
2. Asegúrate de tener el `terraform.tfvars` listo para pegar (lo recreas en el Paso 1).
3. Si tienes infra de antes, haz `terraform destroy` primero para empezar limpio.

---

## PARTE 0 — Introducción (cámara / pantalla de título)

**DECIR:**
> "En este video validamos el ASR de latencia del Sprint 4, el ASR-LAT-01. El
> requisito dice que un reporte que agrega más de 10 millones de registros debe
> responder con un P95 menor o igual a 500 milisegundos. Para lograrlo aplicamos
> el patrón CQRS con una vista materializada: separamos el lado de escritura
> (el microservicio Costos) del lado de consulta (el microservicio Reportes),
> que lee de una vista pre-agregada en MongoDB. El experimento compara dos
> escenarios: hacer la agregación en vivo sobre los datos crudos, contra leer
> la vista materializada ya calculada."

---

## PARTE 1 — Despliegue de infraestructura (Terraform)

**HACER:** En CloudShell:
```bash
cd ~/bite-sprint4/terraform
cat terraform.tfvars      # mostrar brevemente la config (sin enfocar secretos)
terraform init
```

**DECIR (mientras corre init):**
> "Toda la infraestructura está definida como código con Terraform. Aquí
> levantamos el sistema completo en AWS: una instancia EC2 con MongoDB, otra con
> el microservicio de Reportes en Nest.js, además del API Gateway Kong, la base
> de datos relacional y el balanceador. Estoy inicializando Terraform, que
> descarga el proveedor de AWS."

**HACER:**
```bash
terraform apply
# escribir: yes
```

**DECIR (mientras aplica, ~5-10 min — puedes cortar/acelerar el video aquí):**
> "Terraform crea todos los recursos. La instancia de MongoDB es una t2.medium
> con 4 GB de RAM, porque agregar más de 10 millones de documentos en vivo
> requiere memoria. Las instancias, al arrancar, corren un script que instala
> Docker, clona el repositorio y levanta los servicios automáticamente."

**HACER (al terminar):**
```bash
terraform output
```

**DECIR:**
> "Al terminar, Terraform nos entrega las direcciones de los servicios. Estas
> son las URLs del microservicio de Reportes que vamos a usar: el endpoint
> baseline y el endpoint materializado."

> Anota de los outputs: `reports_nest_public_ip`, `mongo_public_ip`,
> `mongo_private_ip`. Las usarás en los siguientes pasos.

---

## PARTE 2 — Cargar los datos (seed + materialización)

**DECIR:**
> "Ahora cargamos los datos. Vamos a sembrar más de 10 millones de documentos de
> costos cloud en MongoDB, todos pertenecientes a un mismo tenant, porque el ASR
> exige que UN reporte agregue más de 10 millones de registros."

**HACER:** Conéctate a la EC2 de MongoDB (consola EC2 → instancia `bite-mongo`
→ Connect → EC2 Instance Connect). Dentro:
```bash
cd ~/bite-sprint4 2>/dev/null && git pull || git clone https://github.com/cmolina12/bite-sprint4.git ~/bite-sprint4
cd ~/bite-sprint4/services/manejador-reportes-nest
npm install
SINGLE_TENANT=acme-corp MONGO_URI="mongodb://localhost:27017" node scripts/seed-costos.js
```

**DECIR (mientras siembra, ~3 min — acelerar video):**
> "Este script inserta 10.5 millones de documentos. Cada documento representa un
> registro de costo: proveedor cloud, servicio, región, fecha y monto. Los
> insertamos en lotes para que sea eficiente."

**HACER (al terminar el seed):**
```bash
MONGO_URI="mongodb://localhost:27017" node scripts/materialize.js
```

**DECIR (mientras materializa, ~25s):**
> "Ahora construimos la vista materializada. Esta es la clave del patrón CQRS:
> la agregación pesada —agrupar por proveedor, servicio y mes y sumar los
> costos— se calcula UNA sola vez, con la operación $merge de MongoDB, y el
> resultado se guarda en una colección aparte. Fíjense que los 10.5 millones de
> documentos se reducen a solo 336 documentos pre-agregados."

---

## PARTE 3 — Demostrar el contraste (los dos endpoints)

**DECIR:**
> "Ahora probamos los dos escenarios directamente contra el microservicio de
> Reportes. Primero el escenario materializado."

**HACER:** (usa tu `reports_nest_public_ip` real)
```bash
curl -s "http://<IP_NEST>:3000/api/reports/acme-corp/materialized?light=1"
```

**DECIR (al ver la respuesta):**
> "El endpoint materializado responde de inmediato. Lee los 336 documentos
> pre-agregados de la vista, sin recalcular nada. El tiempo de query es de unas
> pocas decenas de milisegundos."

**HACER:**
```bash
curl -s -m 40 "http://<IP_NEST>:3000/api/reports/acme-corp/baseline?light=1"
```

**DECIR (mientras espera ~30s y sale el TIMEOUT):**
> "Ahora el escenario baseline, que hace la agregación en vivo sobre los 10.5
> millones de documentos crudos. Esperamos... y como ven, no completa: la
> operación excede el límite de tiempo y el sistema responde con un timeout.
> Esto confirma la hipótesis del ASR: sin vista materializada, agregar en vivo
> sobre este volumen es inviable."

---

## PARTE 4 — Prueba de carga con JMeter (la métrica oficial)

**DECIR:**
> "Para medir el P95 de forma rigurosa, usamos Apache JMeter, que simula
> solicitudes concurrentes. El plan tiene dos grupos de hilos: uno golpea el
> endpoint baseline y otro el materializado."

**HACER:** En JMeter (Mac):
1. Mostrar el árbol del plan (los dos Thread Groups).
2. Click en el nodo raíz → mostrar las variables `HOST` (= IP del Nest), `PORT`, `TENANT`.
3. Dale Play (▶).

**DECIR (mientras corre):**
> "El grupo baseline lanza varias solicitudes concurrentes; cada una intenta la
> agregación en vivo y termina en timeout. El grupo materializado lanza 1000
> solicitudes concurrentes contra la vista pre-agregada."

**HACER:** Cuando termine, abrir **Aggregate Report**.

**DECIR (señalando la tabla):**
> "Estos son los resultados. El baseline tiene 100% de error: ninguna solicitud
> completa, todas dan timeout alrededor de 30 segundos. En cambio, el endpoint
> materializado procesó las 1000 solicitudes con 0% de error, y su P95 —la
> columna 95% Line— es de 271 milisegundos. Eso está muy por debajo del umbral
> de 500 milisegundos que exige el ASR-LAT-01. El requisito se cumple."

---

## PARTE 5 — Cierre

**DECIR:**
> "En resumen: la agregación en vivo sobre más de 10 millones de registros es
> inviable, con 100% de fallos por timeout. La vista materializada, en cambio,
> responde con un P95 de 271 milisegundos bajo carga concurrente, cumpliendo el
> ASR-LAT-01 con amplio margen. Esto valida la decisión arquitectónica de usar
> CQRS con vista materializada: separar el lado de consulta y pre-agregar los
> datos convierte una operación imposible en una respuesta de milisegundos."

**(Opcional, si quieres mostrar limpieza):**
> "Finalmente, destruimos la infraestructura con terraform destroy para no
> consumir recursos."

---

## RESUMEN DE NÚMEROS (para no equivocarte al narrar)

| Métrica | Baseline | Materializado |
|---|---|---|
| P95 (95% Line) | ~30,300 ms (timeout) | **271 ms** |
| Error % | 100% | 0% |
| Samples | 15 | 1000 |
| Veredicto | Inviable | **Cumple ≤ 500 ms** |

- Documentos crudos: **10,500,000** (un solo tenant: acme-corp)
- Documentos en la vista materializada: **336**
- Umbral ASR-LAT-01: **P95 ≤ 500 ms** → cumplido

---

## NOTAS PRÁCTICAS

- Las IPs cambian en cada `terraform apply`. Usa siempre las de `terraform output`.
- Si el baseline tarda mucho en el video, puedes reducir en el plan JMeter los
  hilos/loops del grupo baseline a 2x1 (con 2 timeouts ya se ve el punto).
- El `BASELINE_MAX_MS=30000` ya viene en el Terraform actualizado, así que el
  contenedor arranca con el timeout de 30s sin configurarlo a mano.
- Acuérdate de `terraform destroy` al final para no gastar créditos.
