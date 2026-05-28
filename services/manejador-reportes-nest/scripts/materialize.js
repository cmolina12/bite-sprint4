/**
 * materialize.js — Construye la vista materializada `reportes_agregados`
 * a partir de la colección cruda `costos` usando $merge.
 *
 * Lado Query del CQRS: la agregación pesada se paga UNA sola vez aquí, no en
 * cada consulta. Debe correrse una vez, ENTRE la prueba baseline y la
 * materializada del experimento.
 *
 * IMPORTANTE: el pipeline de $group aquí es el MISMO que usa el endpoint
 * baseline en vivo (ReportesService.groupPipeline), pero SIN el $match por
 * tenant — materializamos para todos los tenants de una vez.
 *
 * Uso:
 *   MONGO_URI="mongodb://localhost:27017" node scripts/materialize.js
 */
const { MongoClient } = require('mongodb');

const MONGO_URI = process.env.MONGO_URI || 'mongodb://localhost:27017';
const MONGO_DB = process.env.MONGO_DB || 'bite';

const PIPELINE = [
  {
    $group: {
      _id: {
        tenant_id: '$tenant_id',
        provider: '$provider',
        service: '$service',
        year: { $year: '$date' },
        month: { $month: '$date' },
      },
      total_cost: { $sum: '$cost' },
      total_usage: { $sum: '$usage_qty' },
      n_records: { $sum: 1 },
    },
  },
  {
    $project: {
      _id: 0,
      tenant_id: '$_id.tenant_id',
      provider: '$_id.provider',
      service: '$_id.service',
      year: '$_id.year',
      month: '$_id.month',
      total_cost: { $round: ['$total_cost', 2] },
      total_usage: { $round: ['$total_usage', 2] },
      n_records: 1,
    },
  },
  {
    $merge: {
      into: 'reportes_agregados',
      whenMatched: 'replace',
      whenNotMatched: 'insert',
    },
  },
];

async function main() {
  const client = new MongoClient(MONGO_URI);
  await client.connect();
  const db = client.db(MONGO_DB);

  console.log('Construyendo vista materializada `reportes_agregados` con $merge ...');
  const t0 = Date.now();
  await db.collection('costos').aggregate(PIPELINE, { allowDiskUse: true }).toArray();
  console.log(`Vista materializada construida en ${((Date.now() - t0) / 1000).toFixed(1)}s`);

  const view = db.collection('reportes_agregados');
  await view.createIndex({ tenant_id: 1, year: 1, month: 1 });
  console.log(`Documentos en la vista: ${(await view.estimatedDocumentCount()).toLocaleString()}`);
  console.log('Listo.');
  await client.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
