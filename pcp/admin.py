from __future__ import annotations

from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from .models import (
    MovimentacaoEstoquePCP,
    PcpAlertaEnviado,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpEvidenciaManutencao,
    PcpEventoAuditoriaManutencao,
    PcpExecucaoManutencao,
    PcpParametroAlerta,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    PcpProgramacaoAlertaManutencao,
)


class ReadOnlyOperationalAdminMixin:
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: models.Model | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: models.Model | None = None) -> bool:
        return False


@admin.register(PcpAreaProducao)
class PcpAreaProducaoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "ativo", "updated_at")
    list_filter = ("ativo",)
    search_fields = ("codigo", "nome")


@admin.register(PcpAtivo)
class PcpAtivoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "area", "status", "criticidade", "ativo")
    list_filter = ("status", "criticidade", "area", "ativo")
    search_fields = ("codigo", "nome", "numero_serie")
    autocomplete_fields = ("area",)


@admin.register(PcpPlanoManutencao)
class PcpPlanoManutencaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo_pcp", "tipo", "intervalo_dias", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("nome", "ativo_pcp__codigo", "ativo_pcp__nome")
    autocomplete_fields = ("ativo_pcp",)


@admin.register(PcpProgramacaoManutencao)
class PcpProgramacaoManutencaoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("get_ativo_pcp", "plano", "data_prevista", "status", "origem", "ativo")
    list_filter = ("status", "origem", "ativo", "data_prevista")
    search_fields = ("plano__ativo_pcp__codigo", "plano__ativo_pcp__nome", "plano__nome")
    autocomplete_fields = ("plano",)
    date_hierarchy = "data_prevista"

    @admin.display(description="Ativo", ordering="plano__ativo_pcp__codigo")
    def get_ativo_pcp(self, obj: PcpProgramacaoManutencao) -> str:
        return str(obj.plano.ativo_pcp)


@admin.register(PcpExecucaoManutencao)
class PcpExecucaoManutencaoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("ativo_pcp", "tipo", "data_inicio", "data_fim", "responsavel", "ativo")
    list_filter = ("tipo", "ativo", "data_inicio")
    search_fields = ("ativo_pcp__codigo", "ativo_pcp__nome", "observacao")
    autocomplete_fields = ("ativo_pcp", "programacao", "responsavel")
    date_hierarchy = "data_inicio"


@admin.register(PcpDowntime)
class PcpDowntimeAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("ativo_pcp", "categoria", "tipo", "inicio", "fim", "duracao_minutos", "origem", "ativo")
    list_filter = ("categoria", "tipo", "origem", "ativo", "inicio")
    search_fields = ("ativo_pcp__codigo", "ativo_pcp__nome", "motivo")
    autocomplete_fields = ("ativo_pcp", "responsavel")
    date_hierarchy = "inicio"


@admin.register(PcpParametroAlerta)
class PcpParametroAlertaAdmin(admin.ModelAdmin):
    list_display = ("ativo_pcp", "area", "dias_antecedencia", "alertar_preventiva", "alertar_downtime_aberto", "ativo")
    list_filter = ("alertar_preventiva", "alertar_downtime_aberto", "ativo")
    search_fields = ("ativo_pcp__codigo", "ativo_pcp__nome", "area__codigo", "area__nome", "emails_destino")
    autocomplete_fields = ("ativo_pcp", "area")


@admin.register(PcpAlertaEnviado)
class PcpAlertaEnviadoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("tipo_alerta", "data_referencia", "assunto", "status", "tentativas", "enviado_em", "ativo")
    list_filter = ("tipo_alerta", "status", "data_referencia", "enviado_em", "ativo")
    search_fields = ("chave_idempotencia", "assunto", "destinatarios")
    autocomplete_fields = ("parametro", "programacao", "downtime")
    date_hierarchy = "data_referencia"


@admin.register(PcpProgramacaoAlertaManutencao)
class PcpProgramacaoAlertaManutencaoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("programacao", "dias_antecedencia", "data_disparo", "status", "tentativas", "enviado_em")
    list_filter = ("status", "dias_antecedencia", "data_disparo")
    search_fields = ("programacao__plano__ativo_pcp__codigo", "destinatarios")
    autocomplete_fields = ("programacao",)
    date_hierarchy = "data_disparo"


@admin.register(PcpEvidenciaManutencao)
class PcpEvidenciaManutencaoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = (
        "nome_original",
        "execucao",
        "finalidade",
        "tipo",
        "tamanho_bytes",
        "enviado_por",
        "created_at",
        "ativo",
    )
    list_filter = ("finalidade", "tipo", "ativo", "created_at")
    search_fields = ("nome_original", "sha256", "execucao__ativo_pcp__codigo")
    autocomplete_fields = ("execucao", "enviado_por")


@admin.register(PcpEventoAuditoriaManutencao)
class PcpEventoAuditoriaManutencaoAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("execucao", "tipo_evento", "usuario", "criado_em")
    list_filter = ("tipo_evento", "criado_em")
    search_fields = ("execucao__ativo_pcp__codigo", "justificativa")
    autocomplete_fields = ("execucao", "usuario")
    date_hierarchy = "criado_em"


@admin.register(MovimentacaoEstoquePCP)
class MovimentacaoEstoquePCPAdmin(ReadOnlyOperationalAdminMixin, admin.ModelAdmin):
    list_display = ("filial", "produto_codigo", "data_movimentacao", "tipo_movimentacao", "origem_movimentacao", "quantidade", "ativo")
    list_filter = ("filial", "tipo_movimentacao", "origem_movimentacao", "ativo", "data_movimentacao")
    search_fields = ("produto_codigo", "documento", "cf_operacao")
    date_hierarchy = "data_movimentacao"
