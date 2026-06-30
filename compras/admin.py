from django.contrib import admin

from .models import (
    AvaliacaoFornecedor,
    ComprasSyncLog,
    PerguntaAvaliacao,
    PmsCustoTarefa,
    PmsEdt,
    PmsProjeto,
    PmsTarefa,
    RespostaAvaliacao,
)

@admin.register(PerguntaAvaliacao)
class PerguntaAvaliacaoAdmin(admin.ModelAdmin):
    list_display = ('texto', 'ativa', 'ordem')
    list_editable = ('ativa', 'ordem')
    ordering = ('ordem',)

admin.site.register(AvaliacaoFornecedor)
admin.site.register(RespostaAvaliacao)


@admin.register(PmsProjeto)
class PmsProjetoAdmin(admin.ModelAdmin):
    list_display = ('projeto', 'revisao', 'filial', 'descricao', 'atualizado_em')
    search_fields = ('projeto', 'revisao', 'descricao')
    list_filter = ('filial', 'revisao')


@admin.register(PmsEdt)
class PmsEdtAdmin(admin.ModelAdmin):
    list_display = ('projeto', 'revisao', 'edt', 'edt_pai', 'nivel', 'descricao', 'custo_previsto')
    search_fields = ('projeto', 'revisao', 'edt', 'edt_pai', 'descricao')
    list_filter = ('filial', 'revisao', 'nivel')


@admin.register(PmsTarefa)
class PmsTarefaAdmin(admin.ModelAdmin):
    list_display = ('projeto', 'revisao', 'tarefa', 'edt', 'descricao', 'custo_previsto')
    search_fields = ('projeto', 'revisao', 'tarefa', 'edt', 'descricao')
    list_filter = ('filial', 'revisao')


@admin.register(PmsCustoTarefa)
class PmsCustoTarefaAdmin(admin.ModelAdmin):
    list_display = (
        'projeto',
        'revisao',
        'tarefa',
        'edt',
        'custo_previsto',
        'custo_realizado',
        'custo_empenhado',
        'saldo_previsto_realizado',
    )
    search_fields = ('projeto', 'revisao', 'tarefa', 'edt')
    list_filter = ('filial', 'revisao')


@admin.register(ComprasSyncLog)
class ComprasSyncLogAdmin(admin.ModelAdmin):
    list_display = ('nome', 'status', 'iniciado_em', 'finalizado_em', 'linhas_lidas', 'linhas_gravadas')
    search_fields = ('nome', 'mensagem', 'erro')
    list_filter = ('nome', 'status')
    readonly_fields = (
        'nome',
        'status',
        'iniciado_em',
        'finalizado_em',
        'arquivos_processados',
        'linhas_lidas',
        'linhas_gravadas',
        'mensagem',
        'erro',
        'executado_por',
    )
