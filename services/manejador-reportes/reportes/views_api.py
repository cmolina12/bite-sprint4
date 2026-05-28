"""
Vistas REST de la API de reportes.

En esta Etapa 1, las vistas son funcionales pero SIN validación de tenant
(eso se añade en Etapa 3 vía middleware). Los endpoints existen para que el
ALB tenga algo que responder en el Experimento 1 (validar round-robin).

Endpoints:
  GET  /api/tenants/                    — Lista de tenants (debug, no protegido)
  GET  /api/reports/<tenant_slug>/      — Reportes de un tenant
  POST /api/reports/<tenant_slug>/      — Crear reporte (para seed de datos)
  GET  /api/reports/<tenant_slug>/<id>/ — Detalle de un reporte
"""

import json
import logging
import time

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Tenant, Report, AuditLog

logger = logging.getLogger(__name__)


def _report_to_dict(report):
    return {
        "id": report.id,
        "tenant": report.tenant.slug,
        "title": report.title,
        "period": report.period,
        "total_cost_usd": str(report.total_cost_usd),
        "payload": report.payload,
        "created_at": report.created_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET"])
def list_tenants(request):
    """Lista los tenants registrados. Útil para verificar seed."""
    tenants = Tenant.objects.filter(is_active=True).values(
        "id", "name", "slug", "is_active", "created_at"
    )
    return JsonResponse({
        "count": len(tenants),
        "tenants": list(tenants),
        "served_by": settings.INSTANCE_ID,
    }, json_dumps_params={"default": str})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def reports_for_tenant(request, tenant_slug):
    """
    GET  → lista reportes del tenant
    POST → crea un reporte nuevo (sin auth en Etapa 1; en Etapa 3 lo protegemos)
    """
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)

    if request.method == "GET":
        # Simulamos un poco de trabajo de "generación de reporte"
        # — esto hace que el Circuit Breaker tenga algo que medir en Exp 1.
        start = time.time()
        reports = Report.objects.filter(tenant=tenant).order_by("-created_at")[:50]
        elapsed_ms = int((time.time() - start) * 1000)

        return JsonResponse({
            "tenant": tenant.slug,
            "count": reports.count(),
            "reports": [_report_to_dict(r) for r in reports],
            "served_by": settings.INSTANCE_ID,
            "query_time_ms": elapsed_ms,
        })

    # POST — crear reporte
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    report = Report.objects.create(
        tenant=tenant,
        title=data.get("title", "Untitled report"),
        period=data.get("period", "2026-Q1"),
        total_cost_usd=data.get("total_cost_usd", 0),
        payload=data.get("payload", {}),
    )
    logger.info("Created report %s for tenant %s", report.id, tenant.slug)
    return JsonResponse(_report_to_dict(report), status=201)


@csrf_exempt
@require_http_methods(["GET"])
def report_detail(request, tenant_slug, report_id):
    """Detalle de un reporte específico."""
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
    report = get_object_or_404(Report, id=report_id, tenant=tenant)
    return JsonResponse({
        **_report_to_dict(report),
        "served_by": settings.INSTANCE_ID,
    })


@csrf_exempt
@require_http_methods(["GET"])
def audit_summary(request):
    """
    Endpoint de SOLO LECTURA para verificar el AuditLog (Experimento 2, paso 4).

    Devuelve el conteo y una muestra de entradas del AuditLog, con sus campos
    de trazabilidad (timestamp, usuario, recurso solicitado). Lo consume el
    script del experimento para confirmar que los intentos cross-tenant quedaron
    registrados.

    Filtros por query string (todos opcionales):
      outcome           — ej: unauthorized_tenant
      user_sub          — subject del JWT atacante
      requested_tenant  — slug del tenant víctima (ej: globex-inc)
      since             — ISO 8601; solo entradas posteriores (aísla una corrida)
      limit             — máx. de entradas en la muestra (default 50, tope 200)

    Nota: en producción este endpoint iría protegido (solo admin). Aquí queda
    abierto a propósito para que el experimento sea reproducible y autocontenido.
    """
    qs = AuditLog.objects.all()

    outcome = request.GET.get("outcome")
    if outcome:
        qs = qs.filter(outcome=outcome)

    user_sub = request.GET.get("user_sub")
    if user_sub:
        qs = qs.filter(user_sub=user_sub)

    requested_tenant = request.GET.get("requested_tenant")
    if requested_tenant:
        qs = qs.filter(requested_tenant_slug=requested_tenant)

    since_raw = request.GET.get("since")
    if since_raw:
        since_dt = parse_datetime(since_raw)
        if since_dt is None:
            return HttpResponseBadRequest("Invalid 'since' (use ISO 8601)")
        qs = qs.filter(timestamp__gte=since_dt)

    try:
        limit = min(int(request.GET.get("limit", "50")), 200)
    except ValueError:
        return HttpResponseBadRequest("Invalid 'limit'")

    total = qs.count()
    entries = [
        {
            "timestamp": e.timestamp.isoformat(),
            "user_sub": e.user_sub,
            "user_tenant_slug": e.user_tenant_slug,
            "requested_tenant_slug": e.requested_tenant_slug,
            "method": e.method,
            "path": e.path,
            "outcome": e.outcome,
            "source_ip": e.source_ip,
            "handled_by_instance": e.handled_by_instance,
        }
        for e in qs[:limit]
    ]

    return JsonResponse({
        "count": total,
        "returned": len(entries),
        "served_by": settings.INSTANCE_ID,
        "entries": entries,
    })
