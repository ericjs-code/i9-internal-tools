from django.contrib import admin
from .models import Equipamento, Local, TipoNC, RNC, RNCImagem


# --- Configuração das Tabelas de Domínio ---
@admin.register(Equipamento)
class EquipamentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(TipoNC)
class TipoNCAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)


# --- Configuração da Imagem em Linha (1:N) ---
class RNCImagemInline(admin.TabularInline):
    model = RNCImagem
    extra = 1
    fields = ('imagem', 'enviado_em')
    readonly_fields = ('enviado_em',)


# --- Configuração da Entidade Principal (RNC) ---
@admin.register(RNC)
class RNCAdmin(admin.ModelAdmin):
    list_display = ('id', 'projeto_cod', 'detector', 'classificacao', 'criticidade', 'status', 'data_abertura')
    list_filter = ('status', 'criticidade', 'classificacao', 'detector', 'data_abertura', 'local')
    search_fields = ('id', 'projeto_cod', 'elemento_rastreador', 'descricao')

    # Interface otimizada para campos ManyToMany (Responsáveis)
    filter_horizontal = ('responsaveis',)

    # Campos que não devem ser editados manualmente por questões de auditoria
    readonly_fields = ('data_abertura', 'criado_em', 'atualizado_em', 'versao')

    # Adiciona as imagens na mesma página da RNC
    inlines = [RNCImagemInline]

    fieldsets = (
        ('Identificação e Origem', {
            'fields': ('registrador', 'projeto_cod', 'elemento_rastreador', 'data_abertura')
        }),
        ('Classificação', {
            'fields': ('detector', 'classificacao', 'criticidade', 'justificativa_criticidade', 'status')
        }),
        ('Domínios', {
            'fields': ('equipamento', 'local', 'tipo_nc')
        }),
        ('Análise e Ação', {
            'fields': ('descricao', 'correcao', 'ishikawa_link', 'causas_principais', 'acao_corretiva')
        }),
        ('Verificação e Prazos', {
            'fields': ('eficacia_texto', 'eficacia_pdf', 'responsaveis', 'data_prevista_conclusao', 'data_encerramento')
        }),
        ('Auditoria', {
            'fields': ('versao', 'criado_em', 'atualizado_em'),
            'classes': ('collapse',)
        }),
    )
