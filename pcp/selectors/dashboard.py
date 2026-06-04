from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from pcp.models import PcpAtivo, PcpDowntime, PcpProgramacaoManutencao, StatusAtivo, StatusManutencao


class PcpDashboardSelector:
    @staticmethod
    def get_context(*, dias: int = 30) -> dict[str, Any]:
        hoje = timezone.localdate()
        data_inicio = hoje - timedelta(days=dias)
        data_limite_preventivas = hoje + timedelta(days=dias)

        ativos = PcpAtivo.objects.select_related("area")
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
        downtimes_periodo = PcpDowntime.objects.select_related("ativo_pcp").filter(inicio__date__gte=data_inicio)
        minutos_parados = int(
            downtimes_periodo.filter(duracao_minutos__isnull=False).aggregate(total=Sum("duracao_minutos"))["total"]
            or 0
        )
        top_downtime = list(
            downtimes_periodo.filter(duracao_minutos__isnull=False)
            .values("ativo_pcp__codigo", "ativo_pcp__nome")
            .annotate(total_minutos=Sum("duracao_minutos"), total_eventos=Count("id"))
            .order_by("-total_minutos")[:8]
        )

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
            "horas_paradas": round(minutos_parados / 60, 1),
            "disponibilidade_estimativa": PcpDashboardSelector._calcular_disponibilidade_estimada(
                total_ativos=contagens_ativos["total"],
                dias=dias,
                minutos_parados=minutos_parados,
            ),
            "downtimes_abertos": downtimes_abertos[:10],
            "preventivas_atrasadas": preventivas_atrasadas[:10],
            "preventivas_proximas": preventivas_proximas[:10],
            "ativos_criticos": ativos.filter(criticidade="critica").order_by("codigo")[:10],
            "top_downtime": top_downtime,
            "top_downtime_labels": [item["ativo_pcp__codigo"] or "N/A" for item in top_downtime],
            "top_downtime_data": [int(item["total_minutos"] or 0) for item in top_downtime],
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
            PcpDowntime.objects.select_related("ativo_pcp", "ativo_pcp__area", "responsavel")
            .filter(fim__isnull=True)
            .order_by("inicio")
        )

    @staticmethod
    def _preventivas_atrasadas(*, hoje: date) -> QuerySet[PcpProgramacaoManutencao]:
        return (
            PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp", "plano__ativo_pcp__area")
            .filter(status=StatusManutencao.PLANEJADA, data_prevista__lt=hoje)
            .order_by("data_prevista")
        )

    @staticmethod
    def _preventivas_proximas(*, hoje: date, limite: date) -> QuerySet[PcpProgramacaoManutencao]:
        return (
            PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp", "plano__ativo_pcp__area")
            .filter(
                status=StatusManutencao.PLANEJADA,
                data_prevista__gte=hoje,
                data_prevista__lte=limite,
            )
            .order_by("data_prevista")
        )

    @staticmethod
    def _calcular_disponibilidade_estimada(*, total_ativos: int, dias: int, minutos_parados: int) -> float:
        minutos_planejados = total_ativos * dias * 24 * 60
        if minutos_planejados <= 0:
            return 100.0
        disponibilidade = ((minutos_planejados - minutos_parados) / minutos_planejados) * 100
        return round(max(0.0, min(100.0, disponibilidade)), 2)
