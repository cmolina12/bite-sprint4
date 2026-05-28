import { Injectable, OnModuleDestroy, Logger } from '@nestjs/common';
import { MongoClient, Db } from 'mongodb';

/**
 * Conexión única a MongoDB compartida por el servicio.
 *
 * Reportes es el lado de QUERIES del CQRS: solo lee. Lee de:
 *   - `costos`              → colección cruda (+10M docs)  [endpoint baseline]
 *   - `reportes_agregados`  → vista materializada          [endpoint materializado]
 */
@Injectable()
export class MongoService implements OnModuleDestroy {
  private readonly logger = new Logger(MongoService.name);
  private client: MongoClient | null = null;
  private db: Db | null = null;

  private readonly uri =
    process.env.MONGO_URI || 'mongodb://localhost:27017';
  private readonly dbName = process.env.MONGO_DB || 'bite';

  async getDb(): Promise<Db> {
    if (this.db) return this.db;
    this.logger.log(`Conectando a MongoDB (${this.dbName})...`);
    this.client = new MongoClient(this.uri, {
      // Pool moderado: bajo carga de JMeter no queremos agotar conexiones.
      maxPoolSize: Number(process.env.MONGO_POOL || 20),
    });
    await this.client.connect();
    this.db = this.client.db(this.dbName);
    this.logger.log('Conexión a MongoDB establecida.');
    return this.db;
  }

  async onModuleDestroy() {
    if (this.client) {
      await this.client.close();
      this.logger.log('Conexión a MongoDB cerrada.');
    }
  }
}
