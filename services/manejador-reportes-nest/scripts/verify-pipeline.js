/**
 * verify-pipeline.js — Valida la LÓGICA del pipeline de agregación SIN MongoDB.
 *
 * No podemos levantar mongod en este entorno (descarga bloqueada), así que
 * replicamos en JS puro el $group/$project del baseline y la materialización,
 * y verificamos contra un cálculo independiente que el resultado es correcto.
 *
 * Esto NO reemplaza la prueba end-to-end en AWS — verifica que la agregación
 * que le pedimos a MongoDB calcula lo que esperamos (costo total por
 * tenant/provider/service/mes).
 */

// --- Generamos un dataset pequeño y determinista (mismo esquema que seed) ---
const docs = [];
function d(tenant, provider, service, y, m, day, cost, usage) {
  docs.push({
    tenant_id: tenant,
    provider,
    service,
    region: 'us-east-1',
    date: new Date(Date.UTC(y, m - 1, day)),
    cost,
    usage_qty: usage,
    resource_id: 'res-000001',
  });
}

// acme-corp / aws / EC2 / 2024-01  → 3 docs
d('acme-corp', 'aws', 'EC2', 2024, 1, 5, 10.0, 100);
d('acme-corp', 'aws', 'EC2', 2024, 1, 12, 20.0, 200);
d('acme-corp', 'aws', 'EC2', 2024, 1, 28, 5.5, 50);
// acme-corp / aws / EC2 / 2024-02 → 1 doc (mes distinto, grupo distinto)
d('acme-corp', 'aws', 'EC2', 2024, 2, 3, 7.25, 70);
// acme-corp / gcp / BigQuery / 2024-01 → 2 docs
d('acme-corp', 'gcp', 'BigQuery', 2024, 1, 9, 3.0, 30);
d('acme-corp', 'gcp', 'BigQuery', 2024, 1, 19, 4.0, 40);
// globex-inc / azure / Functions / 2024-01 → 1 doc (otro tenant)
d('globex-inc', 'azure', 'Functions', 2024, 1, 1, 99.0, 999);

// --- Réplica en JS del pipeline groupPipeline('acme-corp') ---
function aggregateForTenant(rows, tenantId) {
  const groups = new Map();
  for (const r of rows) {
    if (r.tenant_id !== tenantId) continue; // $match
    const key = [
      r.tenant_id,
      r.provider,
      r.service,
      r.date.getUTCFullYear(),
      r.date.getUTCMonth() + 1,
    ].join('|');
    if (!groups.has(key)) {
      groups.set(key, {
        tenant_id: r.tenant_id,
        provider: r.provider,
        service: r.service,
        year: r.date.getUTCFullYear(),
        month: r.date.getUTCMonth() + 1,
        total_cost: 0,
        total_usage: 0,
        n_records: 0,
      });
    }
    const g = groups.get(key);
    g.total_cost += r.cost; // $sum
    g.total_usage += r.usage_qty; // $sum
    g.n_records += 1; // $sum 1
  }
  return [...groups.values()].map((g) => ({
    ...g,
    total_cost: Math.round(g.total_cost * 100) / 100, // $round 2
    total_usage: Math.round(g.total_usage * 100) / 100,
  }));
}

// --- Verificación ---
function assert(name, cond) {
  console.log(`  [${cond ? 'OK' : 'FALLA'}] ${name}`);
  return cond;
}

const result = aggregateForTenant(docs, 'acme-corp');
const byKey = Object.fromEntries(
  result.map((g) => [`${g.provider}/${g.service}/${g.year}-${g.month}`, g]),
);

console.log('Resultado agregado para acme-corp:');
for (const g of result) {
  console.log(
    `  ${g.provider}/${g.service} ${g.year}-${String(g.month).padStart(2, '0')}: ` +
      `cost=${g.total_cost} usage=${g.total_usage} n=${g.n_records}`,
  );
}
console.log('');

const checks = [];
// Solo acme-corp (globex no debe aparecer)
checks.push(assert('no incluye otros tenants', result.every((g) => g.tenant_id === 'acme-corp')));
// EC2 enero: 3 docs, 10+20+5.5 = 35.5
const ec2Jan = byKey['aws/EC2/2024-1'];
checks.push(assert('EC2 2024-01: n=3', ec2Jan && ec2Jan.n_records === 3));
checks.push(assert('EC2 2024-01: total_cost=35.5', ec2Jan && ec2Jan.total_cost === 35.5));
checks.push(assert('EC2 2024-01: total_usage=350', ec2Jan && ec2Jan.total_usage === 350));
// EC2 febrero: grupo separado por mes
const ec2Feb = byKey['aws/EC2/2024-2'];
checks.push(assert('EC2 2024-02 es grupo separado (n=1)', ec2Feb && ec2Feb.n_records === 1));
// BigQuery enero: 3+4 = 7
const bq = byKey['gcp/BigQuery/2024-1'];
checks.push(assert('BigQuery 2024-01: total_cost=7', bq && bq.total_cost === 7));
// Total de grupos para acme: EC2-ene, EC2-feb, BigQuery-ene = 3
checks.push(assert('acme-corp produce 3 grupos', result.length === 3));

console.log('');
const ok = checks.every(Boolean);
console.log(ok ? 'LÓGICA DE AGREGACIÓN: TODO OK ✓' : 'LÓGICA DE AGREGACIÓN: HAY FALLAS ✗');
process.exit(ok ? 0 : 1);
