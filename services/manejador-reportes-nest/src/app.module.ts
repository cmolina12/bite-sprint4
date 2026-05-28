import { Module } from '@nestjs/common';
import { MongoService } from './mongo/mongo.service';
import { ReportesController } from './reportes/reportes.controller';
import { ReportesService } from './reportes/reportes.service';
import { HealthController } from './health/health.controller';

@Module({
  controllers: [ReportesController, HealthController],
  providers: [MongoService, ReportesService],
})
export class AppModule {}
