import { Injectable, Logger } from '@nestjs/common';
import { MongoService } from '../mongo/mongo.service';

/**
 * Lógica del lado QUERY del CQRS.
 *
 * - baseline()    : corre la agregación pesada EN VIVO sobre la colección cruda
 *                   `costos` (+10M docs). Representa el escenario SIN vista
 *                   materializada. Se espera P95 > 2000 ms.
 * - materialized(): lee la vista materializada `reportes_agregados` ya
 *                   pre-agregada. Se espera P95 <= 500 ms (ASR-LAT-01).
 *
 * El MISMO pipeline de agregación (groupPipeline) se usa para construir la vista
 * (en materialize.js, una sola vez) y en el baseline (en cada request). Esa es
 * justamente la comparación que mide el experimento.
 */
@Injectable()
export class ReportesService {
  private readonly logger = new Logger(ReportesService.name);

  constructor(private readonly mongo: MongoService) {}

  /**
   * Pipeline de agregación: costo total por tenant/provider/service/mes.
   * Filtra por tenant para simular el reporte de un analista FinOps concreto.
   */
  static groupPipeline(tenantId: string) {
    return [
      { $match: { tenant_id: tenantId } },
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
    ];
  }

  /** Escenario BASELINE: agregación en vivo sobre la colección cruda. */
  async baseline(tenantId: string) {
    const db = await this.mongo.getDb();
    const start = process.hrtime.bigint();
    const rows = await db
      .collection('costos')
      .aggregate(ReportesService.groupPipeline(tenantId), { allowDiskUse: true })
      .toArray();
    const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
    return {
      mode: 'baseline',
      tenant: tenantId,
      count: rows.length,
      query_time_ms: Math.round(elapsedMs * 100) / 100,
      rows,
    };
  }

  /** Escenario MATERIALIZADO: lectura directa de la vista pre-agregada. */
  async materialized(tenantId: string) {
    const db = await this.mongo.getDb();
    const start = process.hrtime.bigint();
    const rows = await db
      .collection('reportes_agregados')
      .find({ tenant_id: tenantId })
      .toArray();
    const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
    return {
      mode: 'materialized',
      tenant: tenantId,
      count: rows.length,
      query_time_ms: Math.round(elapsedMs * 100) / 100,
      rows,
    };
  }
}
