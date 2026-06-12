from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import TypedDict

from django.db.models import Q

from pcp.models import CategoriaDowntime, PcpDowntime, TipoDowntime
from pcp.services.exceptions import PcpValidationError


class DuracaoAnalytics(TypedDict):
    minutos: int
    horas: float
    dias: float
    legenda: str


class CategoriaAnalytics(DuracaoAnalytics):
    codigo: str
    nome: str


class MotivoAnalytics(DuracaoAnalytics):
    tipo: str
    nome: str
    categoria: str
    categoria_nome: str
    destaque: bool


class AtivoAnalytics(DuracaoAnalytics):
    codigo: str
    nome: str


class DowntimeAnalytics(TypedDict):
    total: DuracaoAnalytics
    categorias: list[CategoriaAnalytics]
    motivos: list[MotivoAnalytics]
    ativos: list[AtivoAnalytics]
    categoria_labels: list[str]
    categoria_horas: list[float]
    motivo_labels: list[str]
    motivo_horas: list[float]


class DowntimeAnalyticsService:
    TIPOS_DESTAQUE = {
        TipoDowntime.FALTA_MAO_OBRA,
        TipoDowntime.FALTA_DESENHO,
    }
    ROTULOS_TIPOS_LEGADOS = {
        "nao_planejado": "Não planejado (legado)",
        "planejado": "Planejado (legado)",
        "setup": "Setup (legado)",
        "qualidade": "Qualidade (legado)",
    }

    @classmethod
    def analisar_periodo(cls, *, inicio: datetime, fim: datetime) -> DowntimeAnalytics:
        if fim <= inicio:
            raise PcpValidationError("O fim do período deve ser posterior ao início.")

        segundos_categoria: defaultdict[str, float] = defaultdict(float)
        segundos_motivo: defaultdict[tuple[str, str], float] = defaultdict(float)
        segundos_ativo: defaultdict[tuple[str, str], float] = defaultdict(float)

        registros = (
            PcpDowntime.objects.filter(inicio__lt=fim)
            .filter(Q(fim__gt=inicio) | Q(fim__isnull=True))
            .values(
                "categoria",
                "tipo",
                "inicio",
                "fim",
                "ativo_pcp__codigo",
                "ativo_pcp__nome",
            )
        )
        for registro in registros.iterator(chunk_size=1000):
            inicio_efetivo = max(registro["inicio"], inicio)
            fim_efetivo = min(registro["fim"] or fim, fim)
            segundos = max(0.0, (fim_efetivo - inicio_efetivo).total_seconds())
            if segundos <= 0:
                continue

            categoria = registro["categoria"]
            tipo = registro["tipo"]
            ativo = (registro["ativo_pcp__codigo"], registro["ativo_pcp__nome"])
            segundos_categoria[categoria] += segundos
            segundos_motivo[(categoria, tipo)] += segundos
            segundos_ativo[ativo] += segundos

        categorias = [
            cls._categoria(codigo=codigo, segundos=segundos_categoria[codigo])
            for codigo in CategoriaDowntime.values
        ]
        motivos = sorted(
            (
                cls._motivo(categoria=categoria, tipo=tipo, segundos=segundos)
                for (categoria, tipo), segundos in segundos_motivo.items()
            ),
            key=lambda item: (-item["minutos"], item["nome"]),
        )
        ativos = sorted(
            (
                cls._ativo(codigo=codigo, nome=nome, segundos=segundos)
                for (codigo, nome), segundos in segundos_ativo.items()
            ),
            key=lambda item: (-item["minutos"], item["codigo"]),
        )[:8]
        total_segundos = sum(segundos_categoria.values())

        return {
            "total": cls._duracao(segundos=total_segundos),
            "categorias": categorias,
            "motivos": motivos,
            "ativos": ativos,
            "categoria_labels": [item["nome"] for item in categorias],
            "categoria_horas": [item["horas"] for item in categorias],
            "motivo_labels": [item["nome"] for item in motivos],
            "motivo_horas": [item["horas"] for item in motivos],
        }

    @classmethod
    def _categoria(cls, *, codigo: str, segundos: float) -> CategoriaAnalytics:
        return {
            "codigo": codigo,
            "nome": CategoriaDowntime(codigo).label,
            **cls._duracao(segundos=segundos),
        }

    @classmethod
    def _motivo(cls, *, categoria: str, tipo: str, segundos: float) -> MotivoAnalytics:
        return {
            "tipo": tipo,
            "nome": cls._rotulo_tipo(tipo=tipo),
            "categoria": categoria,
            "categoria_nome": CategoriaDowntime(categoria).label,
            "destaque": tipo in cls.TIPOS_DESTAQUE,
            **cls._duracao(segundos=segundos),
        }

    @staticmethod
    def _ativo(*, codigo: str, nome: str, segundos: float) -> AtivoAnalytics:
        return {"codigo": codigo, "nome": nome, **DowntimeAnalyticsService._duracao(segundos=segundos)}

    @classmethod
    def _rotulo_tipo(cls, *, tipo: str) -> str:
        try:
            return TipoDowntime(tipo).label
        except ValueError:
            return cls.ROTULOS_TIPOS_LEGADOS.get(tipo, tipo.replace("_", " ").capitalize())

    @staticmethod
    def _duracao(*, segundos: float) -> DuracaoAnalytics:
        minutos = math.ceil(segundos / 60) if segundos > 0 else 0
        horas = round(segundos / 3600, 2)
        dias = round(segundos / 86400, 2)
        dias_inteiros, minutos_restantes = divmod(minutos, 1440)
        horas_inteiras, minutos_finais = divmod(minutos_restantes, 60)
        partes: list[str] = []
        if dias_inteiros:
            partes.append(f"{dias_inteiros} d")
        if horas_inteiras:
            partes.append(f"{horas_inteiras} h")
        if minutos_finais or not partes:
            partes.append(f"{minutos_finais} min")
        return {
            "minutos": minutos,
            "horas": horas,
            "dias": dias,
            "legenda": " ".join(partes),
        }
