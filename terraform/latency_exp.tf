# =============================================================================
# latency_exp.tf — Experimento 1 (ASR-LAT-01): CQRS + Vista Materializada
# =============================================================================
# Despliega lo necesario para el experimento de latencia, en una sola pieza
# adicional a la infra del Sprint 3:
#
#   JMeter → Reportes (Nest.js, EC2 :3000) → MongoDB (EC2 :27017)
#
#   - 1 EC2 con MongoDB en Docker (colección cruda + vista materializada).
#     Disco de 30 GB para los +10M documentos y el espacio temporal de $merge.
#   - 1 EC2 con el microservicio Reportes (Nest.js) en Docker.
#
# Ambas en subnets públicas con security groups restrictivos (mismo patrón que
# el resto del proyecto para ahorrar el costo del NAT Gateway).
# =============================================================================

# -----------------------------------------------------------------------------
# Variables específicas del Experimento 1
# -----------------------------------------------------------------------------
variable "mongo_instance_type" {
  description = "Tipo de EC2 para MongoDB. Con +10M docs en un solo tenant, la agregacion en vivo (baseline) necesita RAM: t2.medium (4GB) es el minimo; si el baseline no termina, subir a t2.large (8GB)."
  type        = string
  default     = "t2.medium"
}

variable "mongo_volume_size" {
  description = "Tamaño del disco EBS de MongoDB en GB. +10M docs + espacio de $merge necesitan holgura."
  type        = number
  default     = 30
}

variable "reports_nest_instance_type" {
  description = "Tipo de EC2 para el microservicio Reportes (Nest.js)."
  type        = string
  default     = "t2.micro"
}

variable "reports_nest_git_repo_url" {
  description = "URL del repo con el código del Sprint 4 (contiene services/manejador-reportes-nest)."
  type        = string
}

variable "reports_nest_git_ref" {
  description = "Branch o tag del repo a clonar."
  type        = string
  default     = "main"
}

variable "mongo_db_name" {
  description = "Nombre de la base de datos de MongoDB."
  type        = string
  default     = "bite"
}

# -----------------------------------------------------------------------------
# Security Groups del Experimento 1
# -----------------------------------------------------------------------------

# MongoDB: solo acepta 27017 desde el SG de Reportes-Nest, y SSH desde tu IP.
resource "aws_security_group" "mongo" {
  name        = "${var.project_name}-sg-mongo"
  description = "MongoDB: solo desde Reportes-Nest + SSH desde tu IP"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "MongoDB desde Reportes-Nest"
    from_port       = 27017
    to_port         = 27017
    protocol        = "tcp"
    security_groups = [aws_security_group.reports_nest.id]
  }

  ingress {
    description = "SSH desde tu IP (debugging / correr seed y materialize)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-mongo"
  }
}

# Reportes-Nest: acepta 3000 desde Kong y desde tu IP (para que JMeter le pegue
# directo o vía Kong), y SSH desde tu IP.
resource "aws_security_group" "reports_nest" {
  name        = "${var.project_name}-sg-reports-nest"
  description = "Microservicio Reportes (Nest.js): app port + SSH"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "App port desde Kong"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.kong.id]
  }

  ingress {
    description = "App port desde tu IP (JMeter directo / pruebas)"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "SSH desde tu IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-reports-nest"
  }
}

# -----------------------------------------------------------------------------
# EC2 MongoDB (Docker)
# -----------------------------------------------------------------------------
locals {
  mongo_user_data = <<-USERDATA
    #!/bin/bash
    set -euo pipefail
    apt-get update -y
    apt-get install -y docker.io
    systemctl enable --now docker

    # MongoDB 7 en Docker, datos persistidos en el volumen EBS montado en /var/lib/docker
    docker run -d --name mongo --restart unless-stopped \
      -p 27017:27017 \
      -v mongodata:/data/db \
      mongo:7
  USERDATA
}

resource "aws_instance" "mongo" {
  ami                    = data.aws_ami.ubuntu_2404.id
  instance_type          = var.mongo_instance_type
  key_name               = var.key_pair_name
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.mongo.id]

  iam_instance_profile = "LabInstanceProfile"

  user_data = local.mongo_user_data

  root_block_device {
    volume_size           = var.mongo_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  tags = {
    Name = "${var.project_name}-mongo"
    Role = "mongodb"
  }
}

# -----------------------------------------------------------------------------
# EC2 Reportes (Nest.js, Docker)
# -----------------------------------------------------------------------------
locals {
  reports_nest_user_data = <<-USERDATA
    #!/bin/bash
    set -euo pipefail
    apt-get update -y
    apt-get install -y docker.io git
    systemctl enable --now docker

    # Clonar el repo del Sprint 4
    cd /opt
    git clone --depth 1 --branch "${var.reports_nest_git_ref}" "${var.reports_nest_git_repo_url}" bite
    cd /opt/bite/services/manejador-reportes-nest

    # Compilar dentro de un contenedor Node para no instalar toolchain en el host,
    # luego construir la imagen final con el Dockerfile del servicio.
    docker run --rm -v "$PWD":/app -w /app node:22-slim \
      sh -c "npm install && npm run build"

    docker build -t bite-reportes-nest .

    # Arrancar el servicio apuntando a la EC2 de MongoDB
    docker run -d --name reportes-nest --restart unless-stopped \
      -p 3000:3000 \
      -e MONGO_URI="mongodb://${aws_instance.mongo.private_ip}:27017" \
      -e MONGO_DB="${var.mongo_db_name}" \
      -e PORT=3000 \
      -e BASELINE_MAX_MS=30000 \
      bite-reportes-nest
  USERDATA
}

resource "aws_instance" "reports_nest" {
  ami                    = data.aws_ami.ubuntu_2404.id
  instance_type          = var.reports_nest_instance_type
  key_name               = var.key_pair_name
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.reports_nest.id]

  iam_instance_profile = "LabInstanceProfile"

  user_data = local.reports_nest_user_data

  # Asegura que Mongo exista primero (necesitamos su private_ip en el user_data)
  depends_on = [aws_instance.mongo]

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  tags = {
    Name = "${var.project_name}-reports-nest"
    Role = "manejador-reportes-nest"
  }
}
