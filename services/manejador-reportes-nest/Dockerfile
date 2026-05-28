# Microservicio Reportes (Nest.js) — lado Query del CQRS, ASR-LAT-01
FROM node:22-slim

WORKDIR /app

# Instalar dependencias (capa cacheable)
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

# Copiar el build ya compilado y los scripts de seed/materialización
COPY dist ./dist
COPY scripts ./scripts

ENV PORT=3000
EXPOSE 3000

CMD ["node", "dist/main.js"]
