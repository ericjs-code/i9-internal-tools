from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from pcp.models import (
    OrigemApontamento,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpItemManutencao,
    PcpPlanoManutencao,
    PcpPlanoManutencaoItem,
    PcpProgramacaoManutencao,
    StatusManutencao,
    StatusAtivo,
    TipoManutencao,
    TipoEventoAuditoria,
)
from pcp.services.audit import AuditoriaManutencaoService
from pcp.services.exceptions import PcpConflictError, PcpValidationError


@dataclass(frozen=True)
class ProgramacaoResultado:
    programacao: PcpProgramacaoManutencao
    criada: bool


@dataclass(frozen=True)
class RecalculoResultado:
    criadas: int
    existentes: int


class PlanoManutencaoService:
    @staticmethod
    def criar_plano(
        *,
        ativo_pcp: PcpAtivo,
        nome: str,
        data_inicio: date,
        tipo: str = TipoManutencao.PREVENTIVA,
        descricao: str = "",
        intervalo_dias: int | None = None,
        itens_manutencao: Iterable[PcpItemManutencao] | None = None,
    ) -> PcpPlanoManutencao:
        PlanoManutencaoService._validar_intervalo(intervalo_dias=intervalo_dias)
        if not nome.strip():
            raise PcpValidationError("Nome do plano é obrigatório.")
        if not ativo_pcp.ativo:
            raise PcpValidationError("Não é permitido criar plano para ativo inativo.")

        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.create(
                ativo_pcp=ativo_pcp,
                nome=nome.strip(),
                tipo=tipo,
                descricao=descricao.strip(),
                intervalo_dias=intervalo_dias,
                data_inicio=data_inicio,
            )
            if itens_manutencao is not None:
                PlanoManutencaoService._sincronizar_itens_manutencao(
                    plano=plano,
                    itens_manutencao=itens_manutencao,
                )
            return plano

    @staticmethod
    def atualizar_plano(
        *,
        plano: PcpPlanoManutencao,
        nome: str,
        data_inicio: date,
        tipo: str = TipoManutencao.PREVENTIVA,
        descricao: str = "",
        intervalo_dias: int | None = None,
        itens_manutencao: Iterable[PcpItemManutencao] | None = None,
    ) -> PcpPlanoManutencao:
        PlanoManutencaoService._validar_intervalo(intervalo_dias=intervalo_dias)
        if not nome.strip():
            raise PcpValidationError("Nome do plano é obrigatório.")

        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.select_for_update().select_related("ativo_pcp").get(pk=plano.pk)
            if not plano.ativo_pcp.ativo:
                raise PcpValidationError("Não é permitido alterar plano de ativo inativo.")
            if PcpProgramacaoManutencao.objects.filter(plano=plano, status=StatusManutencao.EM_EXECUCAO).exists():
                raise PcpConflictError("Plano possui manutenção em execução e não pode ser alterado.")
            plano.nome = nome.strip()
            plano.tipo = tipo
            plano.descricao = descricao.strip()
            plano.intervalo_dias = intervalo_dias
            plano.data_inicio = data_inicio
            plano.save(
                update_fields=["nome", "tipo", "descricao", "intervalo_dias", "data_inicio", "updated_at"]
            )
            if itens_manutencao is not None:
                PlanoManutencaoService._sincronizar_itens_manutencao(
                    plano=plano,
                    itens_manutencao=itens_manutencao,
                )
            return plano

    @staticmethod
    def desativar_plano(*, plano: PcpPlanoManutencao) -> PcpPlanoManutencao:
        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.select_for_update().get(pk=plano.pk)
            if PcpProgramacaoManutencao.objects.filter(plano=plano, status=StatusManutencao.EM_EXECUCAO).exists():
                raise PcpConflictError("Plano possui manutenção em execução e não pode ser desativado.")
            PcpProgramacaoManutencao.objects.filter(plano=plano, status=StatusManutencao.PLANEJADA).update(
                ativo=False,
                status=StatusManutencao.CANCELADA,
                updated_at=timezone.now(),
            )
            plano.ativo = False
            plano.save(update_fields=["ativo", "updated_at"])
            return plano

    @staticmethod
    def _validar_intervalo(*, intervalo_dias: int | None) -> None:
        if intervalo_dias is None or intervalo_dias <= 0:
            raise PcpValidationError("O intervalo de dias deve ser maior que zero.")

    @staticmethod
    def _sincronizar_itens_manutencao(
        *,
        plano: PcpPlanoManutencao,
        itens_manutencao: Iterable[PcpItemManutencao],
    ) -> None:
        itens = list(itens_manutencao)
        item_ids = [item.pk for item in itens]
        if len(item_ids) != len(set(item_ids)):
            raise PcpValidationError("O mesmo item de manutenção não pode ser associado duas vezes ao plano.")

        if not item_ids:
            PcpPlanoManutencaoItem.objects.filter(plano=plano).delete()
            return

        itens_validos = {
            item.pk: item
            for item in PcpItemManutencao.objects.select_for_update().filter(
                pk__in=item_ids,
                ativo=True,
                ativo_pcp=plano.ativo_pcp,
            )
        }
        if len(itens_validos) != len(item_ids):
            raise PcpValidationError("Selecione apenas itens de manutenção ativos e vinculados ao ativo do plano.")

        PcpPlanoManutencaoItem.objects.filter(plano=plano).delete()
        PcpPlanoManutencaoItem.objects.bulk_create(
            [
                PcpPlanoManutencaoItem(
                    plano=plano,
                    item_manutencao=itens_validos[item_id],
                    ordem=ordem,
                )
                for ordem, item_id in enumerate(item_ids, start=1)
            ]
        )


class ProgramacaoManutencaoService:
    STATUS_PENDENTES = (StatusManutencao.PLANEJADA, StatusManutencao.EM_EXECUCAO)

    @staticmethod
    def calcular_data_proxima_preventiva(
        *,
        plano: PcpPlanoManutencao,
        referencia: date | None = None,
    ) -> date:
        if plano.intervalo_dias is None or plano.intervalo_dias <= 0:
            raise PcpValidationError("Plano ativo exige intervalo de dias maior que zero.")

        ultima_execucao = ProgramacaoManutencaoService._ultima_execucao_concluida(plano=plano)
        if ultima_execucao and ultima_execucao.data_fim:
            return timezone.localtime(ultima_execucao.data_fim).date() + timedelta(days=plano.intervalo_dias)
        return plano.data_inicio

    @staticmethod
    def gerar_proxima_preventiva(
        *,
        plano: PcpPlanoManutencao,
        referencia: date | None = None,
        origem: str = OrigemApontamento.SISTEMA,
    ) -> ProgramacaoResultado:
        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.select_for_update().select_related("ativo_pcp").get(pk=plano.pk)
            if not plano.ativo or not plano.ativo_pcp.ativo:
                raise PcpValidationError("Plano e ativo devem estar ativos para gerar programação.")

            existente = ProgramacaoManutencaoService._programacoes_pendentes(plano=plano).first()
            if existente:
                return ProgramacaoResultado(programacao=existente, criada=False)

            data_prevista = ProgramacaoManutencaoService.calcular_data_proxima_preventiva(
                plano=plano,
                referencia=referencia,
            )
            programacao = PcpProgramacaoManutencao.objects.create(
                plano=plano,
                data_prevista=data_prevista,
                data_limite=data_prevista,
                status=StatusManutencao.PLANEJADA,
                origem=origem,
            )
            from pcp.services.alerts import AlertaManutencaoService

            AlertaManutencaoService.sincronizar_programacao(programacao=programacao, referencia=referencia)
            return ProgramacaoResultado(programacao=programacao, criada=True)

    @staticmethod
    def recalcular_preventivas(*, referencia: date | None = None) -> RecalculoResultado:
        planos = PcpPlanoManutencao.objects.select_related("ativo_pcp").filter(
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias__isnull=False,
            ativo_pcp__ativo=True,
        )
        criadas = 0
        existentes = 0

        for plano in planos.iterator(chunk_size=500):
            resultado = ProgramacaoManutencaoService.gerar_proxima_preventiva(
                plano=plano,
                referencia=referencia,
                origem=OrigemApontamento.CELERY,
            )
            if resultado.criada:
                criadas += 1
            else:
                existentes += 1

        return RecalculoResultado(criadas=criadas, existentes=existentes)

    @staticmethod
    def sincronizar_preventiva_do_plano(*, plano: PcpPlanoManutencao, referencia: date | None = None) -> PcpProgramacaoManutencao | None:
        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.select_for_update().select_related("ativo_pcp").get(pk=plano.pk)
            if plano.tipo != TipoManutencao.PREVENTIVA or not plano.ativo or not plano.ativo_pcp.ativo:
                return None
            programacao = (
                ProgramacaoManutencaoService._programacoes_pendentes(plano=plano)
                .select_for_update()
                .filter(status=StatusManutencao.PLANEJADA)
                .first()
            )
            if not programacao:
                return ProgramacaoManutencaoService.gerar_proxima_preventiva(plano=plano, referencia=referencia).programacao

            data_prevista = ProgramacaoManutencaoService.calcular_data_proxima_preventiva(
                plano=plano,
                referencia=referencia,
            )
            programacao.data_prevista = data_prevista
            programacao.data_limite = data_prevista
            programacao.save(update_fields=["data_prevista", "data_limite", "updated_at"])

        from pcp.services.alerts import AlertaManutencaoService

        AlertaManutencaoService.sincronizar_programacao(programacao=programacao, referencia=referencia)
        return programacao

    @staticmethod
    def concluir_execucao(
        *,
        execucao: PcpExecucaoManutencao,
        data_fim: datetime | None = None,
        concluido_por: AbstractBaseUser | None = None,
        diagnostico: str = "",
        servicos_executados: str = "",
        resultado: str = "",
        recomendacoes: str = "",
    ) -> PcpExecucaoManutencao:
        data_fim = data_fim or timezone.now()

        with transaction.atomic():
            execucao = (
                PcpExecucaoManutencao.objects.select_for_update(of=("self",))
                .select_related("programacao__plano", "ativo_pcp__area")
                .get(pk=execucao.pk)
            )
            if execucao.data_fim:
                raise PcpConflictError("Execução já foi concluída.")
            if data_fim <= execucao.data_inicio:
                raise PcpValidationError("A data de fim deve ser posterior à data de início.")

            execucao.data_fim = data_fim
            execucao.concluido_em = timezone.now()
            execucao.concluido_por = concluido_por
            execucao.diagnostico = diagnostico.strip()
            execucao.servicos_executados = servicos_executados.strip()
            execucao.resultado = resultado.strip()
            execucao.recomendacoes = recomendacoes.strip()
            execucao.snapshot_ativo_codigo = execucao.ativo_pcp.codigo
            execucao.snapshot_ativo_nome = execucao.ativo_pcp.nome
            execucao.snapshot_ativo_numero_serie = execucao.ativo_pcp.numero_serie
            execucao.snapshot_area_nome = execucao.ativo_pcp.area.nome
            if execucao.programacao_id:
                execucao.snapshot_plano_nome = execucao.programacao.plano.nome
                execucao.snapshot_plano_tipo = execucao.programacao.plano.tipo
            execucao.save(
                update_fields=[
                    "data_fim",
                    "concluido_em",
                    "concluido_por",
                    "diagnostico",
                    "servicos_executados",
                    "resultado",
                    "recomendacoes",
                    "snapshot_ativo_codigo",
                    "snapshot_ativo_nome",
                    "snapshot_ativo_numero_serie",
                    "snapshot_area_nome",
                    "snapshot_plano_nome",
                    "snapshot_plano_tipo",
                    "updated_at",
                ]
            )
            AuditoriaManutencaoService.registrar(
                execucao=execucao,
                tipo_evento=TipoEventoAuditoria.CONCLUIDA,
                usuario=concluido_por,
                dados={"data_fim": data_fim.isoformat()},
            )

            if execucao.programacao_id:
                execucao.programacao.status = StatusManutencao.CONCLUIDA
                execucao.programacao.save(update_fields=["status", "updated_at"])
                from pcp.services.alerts import AlertaManutencaoService

                AlertaManutencaoService.sincronizar_programacao(programacao=execucao.programacao)
                ProgramacaoManutencaoService.gerar_proxima_preventiva(
                    plano=execucao.programacao.plano,
                    referencia=data_fim.date(),
                    origem=OrigemApontamento.SISTEMA,
                )

            ativo = PcpAtivo.objects.select_for_update().get(pk=execucao.ativo_pcp_id)
            if not PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                ativo.status = StatusAtivo.OPERANDO
                ativo.save(update_fields=["status", "updated_at"])

        return execucao

    @staticmethod
    def iniciar_execucao(
        *,
        ativo_pcp: PcpAtivo,
        tipo: str,
        data_inicio: datetime | None = None,
        responsavel: AbstractBaseUser | None = None,
        programacao: PcpProgramacaoManutencao | None = None,
        observacao: str = "",
    ) -> PcpExecucaoManutencao:
        data_inicio = data_inicio or timezone.now()
        try:
            with transaction.atomic():
                ativo = PcpAtivo.objects.select_for_update().get(pk=ativo_pcp.pk)
                if PcpExecucaoManutencao.objects.filter(ativo_pcp=ativo, data_fim__isnull=True).exists():
                    raise PcpConflictError("Já existe uma execução de manutenção aberta para este ativo.")

                if programacao:
                    programacao = PcpProgramacaoManutencao.objects.select_for_update().select_related("plano").get(
                        pk=programacao.pk
                    )
                    if programacao.plano.ativo_pcp_id != ativo.pk:
                        raise PcpValidationError("A programação não pertence ao ativo informado.")
                    if programacao.plano.tipo != tipo:
                        raise PcpValidationError("O tipo da execução deve corresponder ao tipo do plano.")
                    if programacao.status != StatusManutencao.PLANEJADA:
                        raise PcpConflictError("Somente programações planejadas podem ser iniciadas.")
                    programacao.status = StatusManutencao.EM_EXECUCAO
                    programacao.save(update_fields=["status", "updated_at"])

                execucao = PcpExecucaoManutencao.objects.create(
                    programacao=programacao,
                    ativo_pcp=ativo,
                    tipo=tipo,
                    data_inicio=data_inicio,
                    responsavel=responsavel,
                    observacao=observacao.strip(),
                )
                AuditoriaManutencaoService.registrar(
                    execucao=execucao,
                    tipo_evento=TipoEventoAuditoria.INICIADA,
                    usuario=responsavel,
                    dados={"data_inicio": data_inicio.isoformat()},
                )
                if not PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                    ativo.status = StatusAtivo.MANUTENCAO
                    ativo.save(update_fields=["status", "updated_at"])
                return execucao
        except IntegrityError as exc:
            raise PcpConflictError("Já existe uma execução de manutenção aberta para este ativo.") from exc

    @staticmethod
    def corrigir_execucao_concluida(
        *,
        execucao: PcpExecucaoManutencao,
        usuario: AbstractBaseUser | None,
        justificativa: str,
        observacao: str = "",
        diagnostico: str = "",
        servicos_executados: str = "",
        resultado: str = "",
        recomendacoes: str = "",
    ) -> PcpExecucaoManutencao:
        justificativa_normalizada = justificativa.strip()
        if not justificativa_normalizada:
            raise PcpValidationError("Justificativa obrigatória para corrigir manutenção concluída.")

        with transaction.atomic():
            execucao = PcpExecucaoManutencao.objects.select_for_update().get(pk=execucao.pk)
            if not execucao.data_fim:
                raise PcpConflictError("Somente manutenções concluídas podem ser corrigidas por este fluxo.")

            campos = {
                "observacao": observacao.strip(),
                "diagnostico": diagnostico.strip(),
                "servicos_executados": servicos_executados.strip(),
                "resultado": resultado.strip(),
                "recomendacoes": recomendacoes.strip(),
            }
            alteracoes = {
                campo: {"antes": getattr(execucao, campo), "depois": valor}
                for campo, valor in campos.items()
                if getattr(execucao, campo) != valor
            }
            if not alteracoes:
                raise PcpValidationError("Nenhuma alteração documental foi informada.")

            for campo, valor in campos.items():
                setattr(execucao, campo, valor)
            execucao.save(update_fields=[*campos.keys(), "updated_at"])
            AuditoriaManutencaoService.registrar(
                execucao=execucao,
                tipo_evento=TipoEventoAuditoria.CORRIGIDA,
                usuario=usuario,
                justificativa=justificativa_normalizada,
                dados={"alteracoes": alteracoes},
            )
            return execucao

    @staticmethod
    def _programacoes_pendentes(*, plano: PcpPlanoManutencao) -> QuerySet[PcpProgramacaoManutencao]:
        return PcpProgramacaoManutencao.objects.filter(
            plano=plano,
            status__in=ProgramacaoManutencaoService.STATUS_PENDENTES,
        ).order_by("data_prevista", "id")

    @staticmethod
    def _ultima_execucao_concluida(*, plano: PcpPlanoManutencao) -> PcpExecucaoManutencao | None:
        return (
            PcpExecucaoManutencao.objects.filter(
                programacao__plano=plano,
                data_fim__isnull=False,
            )
            .order_by("-data_fim")
            .first()
        )
