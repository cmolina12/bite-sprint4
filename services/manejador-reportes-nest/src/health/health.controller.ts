import { Controller, Get } from '@nestjs/common';

/** Health check para Kong/ALB (sin auth, no toca MongoDB). */
@Controller()
export class HealthController {
  @Get('health')
  health() {
    return { status: 'ok', service: 'manejador-reportes', ts: new Date().toISOString() };
  }
}
