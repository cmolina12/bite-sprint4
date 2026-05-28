import {
  Controller,
  Get,
  Param,
  Query,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
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
    try {
      const result = await this.reportes.baseline(tenant);
      return light ? this.strip(result) : result;
    } catch (err: any) {
      // El maxTimeMS de la agregación dispara este error cuando el baseline
      // no completa sobre +10M docs. Es el RESULTADO ESPERADO del ASR-LAT-01:
      // la agregación en vivo es inviable. Devolvemos 503 con mensaje claro
      // (en vez de un 500 genérico) para que el experimento/JMeter lo registre
      // de forma legible.
      const isTimeout =
        err?.code === 50 || // MaxTimeMSExpired
        /time limit|exceeded time/i.test(err?.message || '');
      if (isTimeout) {
        throw new HttpException(
          {
            mode: 'baseline',
            tenant,
            status: 'TIMEOUT',
            detail:
              'La agregacion en vivo sobre la coleccion cruda excedio el limite de tiempo. ' +
              'Confirma el ASR-LAT-01: sin vista materializada, el reporte es inviable.',
          },
          HttpStatus.SERVICE_UNAVAILABLE,
        );
      }
      throw err;
    }
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
