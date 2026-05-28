# =============================================================================
# Outputs útiles para conectarte y para las siguientes etapas
# =============================================================================

output "vpc_id" {
  description = "VPC ID — referencia para todas las etapas siguientes"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs de subnets públicas (Kong, ALB, EC2 reportes)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs de subnets privadas (RDS, Redis)"
  value       = aws_subnet.private[*].id
}

# --- Postgres ---
output "rds_endpoint" {
  description = "Endpoint de PostgreSQL"
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "Puerto de PostgreSQL"
  value       = aws_db_instance.postgres.port
}

output "rds_database" {
  description = "Nombre de la BD inicial"
  value       = aws_db_instance.postgres.db_name
}

# --- Redis ---
output "redis_endpoint" {
  description = "Endpoint de ElastiCache Redis"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

# --- Account info ---
output "aws_account_id" {
  description = "ID de la cuenta AWS (Learner Lab)"
  value       = data.aws_caller_identity.current.account_id
}

output "ubuntu_ami_id" {
  description = "AMI de Ubuntu 24.04 más reciente (para usar en EC2 de las próximas etapas)"
  value       = data.aws_ami.ubuntu_2404.id
}

# --- Security Group IDs (para etapas siguientes) ---
output "sg_kong_id" {
  value = aws_security_group.kong.id
}

output "sg_alb_id" {
  value = aws_security_group.alb.id
}

output "sg_reports_id" {
  value = aws_security_group.reports.id
}

# =============================================================================
# Outputs de Etapa 1 (DISP-01)
# =============================================================================

output "alb_dns_name" {
  description = "DNS público del ALB del Manejador de Reportes. Endpoint para validar la app."
  value       = aws_lb.reports.dns_name
}

output "alb_url" {
  description = "URL completa del ALB para usar en curl/JMeter."
  value       = "http://${aws_lb.reports.dns_name}"
}

output "asg_name" {
  description = "Nombre del ASG (útil para 'aws autoscaling describe-auto-scaling-groups')."
  value       = aws_autoscaling_group.reports.name
}

output "target_group_arn" {
  description = "ARN del Target Group (útil para inspeccionar health de instancias)."
  value       = aws_lb_target_group.reports.arn
}

# =============================================================================
# Outputs de Etapa 2 (DISP-02)
# =============================================================================

output "kong_public_ip" {
  description = "IP pública (Elastic IP) de Kong API Gateway"
  value       = aws_eip.kong.public_ip
}

output "kong_proxy_url" {
  description = "URL del proxy Kong (entrada principal del sistema). Reemplaza al ALB como endpoint cliente."
  value       = "http://${aws_eip.kong.public_ip}:8000"
}

output "kong_admin_url" {
  description = "URL del Kong Admin API (solo desde tu IP). Para inspeccionar estado de upstreams."
  value       = "http://${aws_eip.kong.public_ip}:8001"
}

output "rabbitmq_management_url" {
  description = "URL de la UI de gestión de RabbitMQ (Etapa 4). user: bite / pass: bitepass"
  value       = "http://${aws_eip.kong.public_ip}:15672"
}

# =============================================================================
# Outputs del Experimento 1 (ASR-LAT-01) — Latencia
# =============================================================================

output "mongo_private_ip" {
  description = "IP privada de la EC2 de MongoDB (la usa Reportes-Nest internamente)."
  value       = aws_instance.mongo.private_ip
}

output "mongo_public_ip" {
  description = "IP pública de la EC2 de MongoDB (para SSH y correr seed/materialize)."
  value       = aws_instance.mongo.public_ip
}

output "mongo_ssh" {
  description = "Comando SSH a la EC2 de MongoDB."
  value       = "ssh -i <vockey.pem> ubuntu@${aws_instance.mongo.public_ip}"
}

output "reports_nest_public_ip" {
  description = "IP pública de la EC2 del microservicio Reportes (Nest.js)."
  value       = aws_instance.reports_nest.public_ip
}

output "reports_nest_url" {
  description = "URL directa del microservicio Reportes (Nest.js) para JMeter / pruebas."
  value       = "http://${aws_instance.reports_nest.public_ip}:3000"
}

output "exp1_baseline_url" {
  description = "Endpoint baseline (agregacion en vivo) — escenario lento."
  value       = "http://${aws_instance.reports_nest.public_ip}:3000/api/reports/acme-corp/baseline"
}

output "exp1_materialized_url" {
  description = "Endpoint materializado (vista pre-agregada) — escenario rapido."
  value       = "http://${aws_instance.reports_nest.public_ip}:3000/api/reports/acme-corp/materialized"
}
