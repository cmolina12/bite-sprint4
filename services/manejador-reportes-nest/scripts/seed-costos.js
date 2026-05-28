/**
 * seed-costos.js — Siembra la colección cruda `costos` con +10M documentos.
 *
 * Lado Command del CQRS (datos crudos que normalmente escribiría el microservicio
 * Costos). Para el experimento los generamos directamente.
 *
 * Uso:
 *   npm install            # una vez
 *   MONGO_URI="mongodb://localhost:27017" node scripts/seed-costos.js
 *
 * Variables de entorno:
 *   MONGO_URI   (default mongodb://localhost:27017)
 *   MONGO_DB    (default bite)
 *   TOTAL_DOCS  (default 10500000)
 *   BATCH_SIZE  (default 50000)
 */
const { MongoClient } = require('mongodb');

const MONGO_URI = process.env.MONGO_URI || 'mongodb://localhost:27017';
const MONGO_DB = process.env.MONGO_DB || 'bite';
const TOTAL_DOCS = Number(process.env.TOTAL_DOCS || 10_500_000);
const BATCH_SIZE = Number(process.env.BATCH_SIZE || 50_000);

const TENANTS = ['acme-corp', 'globex-inc', 'initech', 'umbrella', 'stark-ind'];
const PROVIDERS = ['aws', 'gcp', 'azure'];
const SERVICES = {
  aws: ['EC2', 'S3', 'RDS', 'Lambda', 'CloudFront', 'EBS'],
  gcp: ['ComputeEngine', 'CloudStorage', 'BigQuery', 'CloudSQL'],
  azure: ['VirtualMachines', 'BlobStorage', 'SQLDatabase', 'Functions'],
};
const REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'sa-east-1', 'ap-south-1'];

const START_DATE = new Date('2024-01-01T00:00:00Z');
const DAYS_RANGE = 730; // 2 años

function rint(n) {
  return Math.floor(Math.random() * n);
}
function pick(arr) {
  return arr[rint(arr.length)];
}
function round(x, d) {
  const f = 10 ** d;
  return Math.round(x * f) / f;
}

function genDoc() {
  const provider = pick(PROVIDERS);
  const service = pick(SERVICES[provider]);
  const date = new Date(START_DATE.getTime() + rint(DAYS_RANGE) * 86400_000);
  return {
    tenant_id: pick(TENANTS),
    provider,
    service,
    region: pick(REGIONS),
    date,
    cost: round(0.01 + Math.random() * 499.99, 4),
    usage_qty: round(1 + Math.random() * 9999, 2),
    resource_id: `res-${String(rint(100000)).padStart(6, '0')}`,
  };
}

async function main() {
  const client = new MongoClient(MONGO_URI);
  await client.connect();
  const col = client.db(MONGO_DB).collection('costos');

  console.log(`Sembrando ${TOTAL_DOCS.toLocaleString()} documentos en ${MONGO_DB}.costos ...`);
  console.log('Limpiando colección previa ...');
  await col.drop().catch(() => {});

  const t0 = Date.now();
  let inserted = 0;
  let batch = [];
  for (let i = 0; i < TOTAL_DOCS; i++) {
    batch.push(genDoc());
    if (batch.length >= BATCH_SIZE) {
      await col.insertMany(batch, { ordered: false });
      inserted += batch.length;
      batch = [];
      const rate = inserted / ((Date.now() - t0) / 1000);
      process.stdout.write(
        `  ${inserted.toLocaleString()}/${TOTAL_DOCS.toLocaleString()}  (${Math.round(rate).toLocaleString()} docs/s)\r`,
      );
    }
  }
  if (batch.length) {
    await col.insertMany(batch, { ordered: false });
    inserted += batch.length;
  }
  console.log(`\nInsertados ${inserted.toLocaleString()} documentos en ${((Date.now() - t0) / 1000).toFixed(1)}s`);

  console.log('Creando índice (tenant_id, date) ...');
  await col.createIndex({ tenant_id: 1, date: 1 });

  console.log(`Total en colección: ${(await col.estimatedDocumentCount()).toLocaleString()}`);
  console.log('Listo.');
  await client.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
