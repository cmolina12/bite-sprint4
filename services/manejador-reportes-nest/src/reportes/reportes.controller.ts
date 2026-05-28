import { Controller, Get, Param, Query } from '@nestjs/common';
import { ReportesService } from './reportes.service';

/**
 * Endpoints del Experimento 1 (latencia):
 *
 *   GET /api/reports/:tenant/baseline      → agregación en vivo (colección cruda)
 *   GET /api/reports/:tenant/materialized  → lectura de la vista materializada
 *
 * JMeter pega a estos dos endpoints y mide el P95 de cada uno para comparar.
 *
 * El query param ?light=1 hace que la respuesta NO incluya las filas (solo el
 * conteo y el tiempo), útil para que JMeter mida latencia sin transferir payloads
 * grandes que sesguen la medición de la red.
 */
@Controller('api/reports')
export class ReportesController {
  constructor(private readonly reportes: ReportesService) {}

  @Get(':tenant/baseline')
  async baseline(
    @Param('tenant') tenant: string,
    @Query('light') light?: string,
  ) {
    const result = await this.reportes.baseline(tenant);
    return light ? this.strip(result) : result;
  }

  @Get(':tenant/materialized')
  async materialized(
    @Param('tenant') tenant: string,
    @Query('light') light?: string,
  ) {
    const result = await this.reportes.materialized(tenant);
    return light ? this.strip(result) : result;
  }

  private strip(result: any) {
    const { rows, ...rest } = result;
    return rest;
  }
}
