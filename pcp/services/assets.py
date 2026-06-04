from __future__ import annotations

from django.db import IntegrityError, transaction

from pcp.models import (
    CriticidadeAtivo,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    StatusAtivo,
)
from pcp.services.exceptions import PcpConflictError, PcpValidationError


class AtivoService:
    @staticmethod
    def criar_area(*, codigo: str, nome: str, descricao: str = "") -> PcpAreaProducao:
        codigo_normalizado = codigo.strip().upper()
        nome_normalizado = nome.strip()
        if not codigo_normalizado or not nome_normalizado:
            raise PcpValidationError("Código e nome da área são obrigatórios.")

        try:
            with transaction.atomic():
                return PcpAreaProducao.objects.create(
                    codigo=codigo_normalizado,
                    nome=nome_normalizado,
                    descricao=descricao.strip(),
                )
        except IntegrityError as exc:
            raise PcpConflictError("Já existe uma área com este código.") from exc

    @staticmethod
    def criar_ativo(
        *,
        codigo: str,
        nome: str,
        area: PcpAreaProducao,
        descricao: str = "",
        fabricante: str = "",
        modelo: str = "",
        numero_serie: str = "",
        status: str = StatusAtivo.OPERANDO,
        criticidade: str = CriticidadeAtivo.MEDIA,
    ) -> PcpAtivo:
        codigo_normalizado = codigo.strip().upper()
        nome_normalizado = nome.strip()
        if not codigo_normalizado or not nome_normalizado:
            raise PcpValidationError("Código e nome do ativo são obrigatórios.")
        try:
            with transaction.atomic():
                area = PcpAreaProducao.objects.select_for_update().get(pk=area.pk)
                return PcpAtivo.objects.create(
                    codigo=codigo_normalizado,
                    nome=nome_normalizado,
                    area=area,
                    descricao=descricao.strip(),
                    fabricante=fabricante.strip(),
                    modelo=modelo.strip(),
                    numero_serie=numero_serie.strip(),
                    status=status,
                    criticidade=criticidade,
                )
        except PcpAreaProducao.DoesNotExist as exc:
            raise PcpValidationError("Não é permitido vincular um ativo a uma área inativa.") from exc
        except IntegrityError as exc:
            raise PcpConflictError("Já existe um ativo com este código.") from exc

    @staticmethod
    def desativar_ativo(*, ativo: PcpAtivo) -> PcpAtivo:
        with transaction.atomic():
            ativo = PcpAtivo.objects.select_for_update().get(pk=ativo.pk)
            possui_operacao_aberta = PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists() or (
                PcpExecucaoManutencao.objects.filter(ativo_pcp=ativo, data_fim__isnull=True).exists()
            )
            if possui_operacao_aberta:
                raise PcpConflictError("Ativo possui downtime ou manutenção aberta.")
            ativo.status = StatusAtivo.INATIVO
            ativo.ativo = False
            ativo.save(update_fields=["status", "ativo", "updated_at"])
        return ativo

    @staticmethod
    def atualizar_ativo(
        *,
        ativo: PcpAtivo,
        codigo: str,
        nome: str,
        area: PcpAreaProducao,
        descricao: str = "",
        fabricante: str = "",
        modelo: str = "",
        numero_serie: str = "",
        criticidade: str = CriticidadeAtivo.MEDIA,
    ) -> PcpAtivo:
        codigo_normalizado = codigo.strip().upper()
        nome_normalizado = nome.strip()
        if not codigo_normalizado or not nome_normalizado:
            raise PcpValidationError("Código e nome do ativo são obrigatórios.")

        try:
            with transaction.atomic():
                ativo = PcpAtivo.objects.select_for_update().get(pk=ativo.pk)
                area = PcpAreaProducao.objects.select_for_update().get(pk=area.pk)
                ativo.codigo = codigo_normalizado
                ativo.nome = nome_normalizado
                ativo.area = area
                ativo.descricao = descricao.strip()
                ativo.fabricante = fabricante.strip()
                ativo.modelo = modelo.strip()
                ativo.numero_serie = numero_serie.strip()
                ativo.criticidade = criticidade
                ativo.save(
                    update_fields=[
                        "codigo",
                        "nome",
                        "area",
                        "descricao",
                        "fabricante",
                        "modelo",
                        "numero_serie",
                        "criticidade",
                        "updated_at",
                    ]
                )
                return ativo
        except PcpAreaProducao.DoesNotExist as exc:
            raise PcpValidationError("Não é permitido vincular um ativo a uma área inativa.") from exc
        except IntegrityError as exc:
            raise PcpConflictError("Já existe um ativo com este código.") from exc
