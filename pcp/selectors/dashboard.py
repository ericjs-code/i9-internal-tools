from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from pcp.models import PcpAtivo, PcpDowntime, PcpProgramacaoManutencao, StatusAtivo, StatusManutencao
from pcp.services.downtime_analytics import DowntimeAnalyticsService


class PcpDashboardSelector:
    @staticmethod
    def get_context(*, dias: int = 90) -> dict[str, Any]:
        hoje = timezone.localdate()
        data_limite_preventivas = hoje + timedelta(days=dias)
        fim_periodo = timezone.now()
        inicio_periodo = fim_periodo - timedelta(days=dias)

        ativos = PcpAtivo.objects.all()
        contagens_ativos = ativos.aggregate(
            total=Count("id"),
            operando=Count("id", filter=Q(status=StatusAtivo.OPERANDO)),
            parados=Count("id", filter=Q(status=StatusAtivo.PARADO)),
            manutencao=Count("id", filter=Q(status=StatusAtivo.MANUTENCAO)),
        )
        downtimes_abertos = PcpDashboardSelector._downtimes_abertos()
        preventivas_atrasadas = PcpDashboardSelector._preventivas_atrasadas(hoje=hoje)
        preventivas_proximas = PcpDashboardSelector._preventivas_proximas(
            hoje=hoje,
            limite=data_limite_preventivas,
        )
        downtime_analytics = DowntimeAnalyticsService.analisar_periodo(
            inicio=inicio_periodo,
            fim=fim_periodo,
        )
        minutos_parados = downtime_analytics["total"]["minutos"]

        return {
            "dias": dias,
            "total_ativos": contagens_ativos["total"],
            "ativos_operando": contagens_ativos["operando"],
            "ativos_parados": contagens_ativos["parados"],
            "ativos_manutencao": contagens_ativos["manutencao"],
            "downtimes_abertos_count": downtimes_abertos.count(),
            "preventivas_atrasadas_count": preventivas_atrasadas.count(),
            "preventivas_proximas_count": preventivas_proximas.count(),
            "minutos_parados": minutos_parados,
            "horas_paradas": downtime_analytics["total"]["horas"],
            "dias_parados": downtime_analytics["total"]["dias"],
            "downtime_analytics": downtime_analytics,
            "disponibilidade_estimativa": PcpDashboardSelector._calcular_disponibilidade_estimada(
                total_ativos=contagens_ativos["total"],
                dias=dias,
                minutos_parados=minutos_parados,
            ),
            "downtimes_abertos": downtimes_abertos[:10],
            "preventivas_atrasadas": preventivas_atrasadas[:10],
            "preventivas_proximas": preventivas_proximas[:10],
            "ativos_criticos": ativos.filter(criticidade="critica").order_by("codigo", "id")[:10],
            "top_downtime": downtime_analytics["ativos"],
            "top_downtime_labels": [item["nome"] or "Ativo sem nome" for item in downtime_analytics["ativos"]],
            "top_downtime_data": [item["horas"] for item in downtime_analytics["ativos"]],
            "downtime_categoria_labels": downtime_analytics["categoria_labels"],
            "downtime_categoria_data": downtime_analytics["categoria_horas"],
            "downtime_motivo_labels": downtime_analytics["motivo_labels"],
            "downtime_motivo_data": downtime_analytics["motivo_horas"],
            "status_labels": ["Operando", "Parado", "Manutenção"],
            "status_data": [
                contagens_ativos["operando"],
                contagens_ativos["parados"],
                contagens_ativos["manutencao"],
            ],
        }

    @staticmethod
    def _downtimes_abertos() -> QuerySet[PcpDowntime]:
        return (
            PcpDowntime.objects.select_related("ativo_pcp", "responsavel")
            .filter(fim__isnull=True)
            .order_by("inicio", "id")
        )

    @staticmethod
    def _preventivas_atrasadas(*, hoje: date) -> QuerySet[PcpProgramacaoManutencao]:
        return (
            PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp")
            .filter(status=StatusManutencao.PLANEJADA, data_prevista__lt=hoje)
            .order_by("data_prevista", "plano__ativo_pcp__codigo", "id")
        )

    @staticmethod
    def _preventivas_proximas(*, hoje: date, limite: date) -> QuerySet[PcpProgramacaoManutencao]:
        return (
            PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp")
            .filter(
                status=StatusManutencao.PLANEJADA,
                data_prevista__gte=hoje,
                data_prevista__lte=limite,
            )
            .order_by("data_prevista", "plano__ativo_pcp__codigo", "id")
        )

    @staticmethod
    def _calcular_disponibilidade_estimada(*, total_ativos: int, dias: int, minutos_parados: int) -> float:
        minutos_planejados = total_ativos * dias * 24 * 60
        if minutos_planejados <= 0:
            return 100.0
        disponibilidade = ((minutos_planejados - minutos_parados) / minutos_planejados) * 100
        return round(max(0.0, min(100.0, disponibilidade)), 2)
