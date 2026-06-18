from django.contrib import admin
from .models import (Funcionario, RegistroAbsenteismo, Vaga, Candidatura,
                     FormularioAdmissional, DependenteAdmissional,
                     CompetenciaDesempenho, AvaliacaoDesempenho,
                     NotaCompetenciaDesempenho, CicloAvaliacaoDesempenho,
                     VinculoAvaliacaoDesempenho)

@admin.register(Vaga)
class VagaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'setor', 'ativa', 'data_criacao')
    list_filter = ('ativa', 'setor')
    search_fields = ('titulo',)

@admin.register(Candidatura)
class CandidaturaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'vaga', 'status', 'lgpd_consentimento', 'data_aplicacao')
    list_filter = ('status', 'vaga', 'lgpd_consentimento')
    search_fields = ('nome_completo', 'email')

@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    # As colunas que vão aparecer na tabela
    list_display = ('nome_completo', 'cpf', 'matricula', 'usuario', 'get_setor_display', 'get_situacao_display')
    # Cria uma barra de pesquisa por nome, cpf ou matrícula
    search_fields = ('nome_completo', 'cpf', 'matricula', 'usuario__username', 'usuario__email')
    # Cria filtros laterais
    list_filter = ('situacao', 'setor')

@admin.register(RegistroAbsenteismo)
class RegistroAbsenteismoAdmin(admin.ModelAdmin):
    list_display = ('funcionario', 'data_referencia', 'horas_falta', 'horas_extras')
    list_filter = ('data_referencia',)
    search_fields = ('funcionario__nome_completo',)


class DependenteAdmissionalInline(admin.TabularInline):
    model = DependenteAdmissional
    extra = 0


@admin.register(FormularioAdmissional)
class FormularioAdmissionalAdmin(admin.ModelAdmin):
    list_display = ('candidato_nome_interno', 'respondido', 'data_geracao', 'data_resposta', 'gerado_por')
    list_filter = ('respondido', 'data_geracao')
    search_fields = ('candidato_nome_interno', 'nome_completo', 'cpf', 'bairro', 'numero_cnh')
    readonly_fields = ('id_formulario', 'data_geracao', 'data_resposta')
    fieldsets = (
        ('Controle interno', {'fields': ('id_formulario', 'gerado_por', 'data_geracao', 'respondido', 'data_resposta', 'candidato_nome_interno', 'observacoes_rh')}),
        ('Dados básicos', {'fields': ('nome_completo', 'cpf', 'funcao_pretendida')}),
        ('CTPS', {'fields': ('pis', 'numero_ctps', 'serie_ctps', 'uf_ctps')}),
        ('Endereço', {'fields': ('cep', 'endereco', 'bairro', 'cidade_estado')}),
        ('Contatos', {'fields': ('telefone_principal', 'contato_recado', 'email')}),
        ('Dados pessoais', {'fields': ('data_nascimento', 'estado_nascimento', 'naturalidade', 'cor_raca', 'grau_instrucao', 'nome_mae', 'nome_pai', 'estado_civil')}),
        ('Documentos', {'fields': ('numero_rg', 'orgao_expedidor', 'uf_rg', 'data_emissao_rg', 'titulo_eleitor', 'zona_eleitoral', 'secao_eleitoral', 'uf_titulo_eleitor', 'reservista', 'numero_cnh', 'validade_cnh', 'estado_cnh')}),
        ('Benefícios e LGPD', {'fields': ('possui_dependentes_ir', 'botina', 'camisa', 'calca', 'utiliza_vale_transporte', 'trajeto_vale_transporte', 'lgpd_consentimento')}),
    )
    inlines = [DependenteAdmissionalInline]


@admin.register(DependenteAdmissional)
class DependenteAdmissionalAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'formulario', 'data_nascimento', 'cpf')
    search_fields = ('nome_completo', 'cpf', 'formulario__candidato_nome_interno')


@admin.register(CompetenciaDesempenho)
class CompetenciaDesempenhoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ordem', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')


class NotaCompetenciaDesempenhoInline(admin.TabularInline):
    model = NotaCompetenciaDesempenho
    extra = 0


@admin.register(AvaliacaoDesempenho)
class AvaliacaoDesempenhoAdmin(admin.ModelAdmin):
    list_display = ('avaliado', 'ano', 'ciclo', 'ciclo_avaliacao', 'status', 'media', 'avaliada_por', 'bloqueada', 'data_avaliacao')
    list_filter = ('ano', 'ciclo', 'status', 'ciencia_gestor', 'ciencia_colaborador', 'bloqueada')
    search_fields = ('avaliado__username', 'avaliado__first_name', 'avaliado__last_name', 'avaliado__email', 'nome_avaliado')
    readonly_fields = ('data_avaliacao', 'atualizado_em')
    inlines = [NotaCompetenciaDesempenhoInline]


@admin.register(CicloAvaliacaoDesempenho)
class CicloAvaliacaoDesempenhoAdmin(admin.ModelAdmin):
    list_display = ('ano', 'ciclo', 'data_inicio', 'data_fim', 'ativo')
    list_filter = ('ano', 'ciclo', 'ativo')
    ordering = ('-ano', '-ciclo')


@admin.register(VinculoAvaliacaoDesempenho)
class VinculoAvaliacaoDesempenhoAdmin(admin.ModelAdmin):
    list_display = ('avaliado', 'gestor_usuario', 'gestor_funcionario', 'setor_avaliado', 'setor_gestor', 'ativo', 'origem')
    list_filter = ('ativo', 'origem', 'setor_avaliado', 'setor_gestor')
    search_fields = (
        'avaliado__nome_completo',
        'avaliado__usuario__username',
        'avaliado__usuario__email',
        'gestor_usuario__username',
        'gestor_usuario__email',
        'gestor_nome_planilha',
    )
    autocomplete_fields = ('avaliado', 'gestor_usuario', 'gestor_funcionario')


@admin.register(NotaCompetenciaDesempenho)
class NotaCompetenciaDesempenhoAdmin(admin.ModelAdmin):
    list_display = ('avaliacao', 'competencia', 'nota')
    list_filter = ('competencia', 'nota')
    search_fields = ('avaliacao__avaliado__username', 'avaliacao__avaliado__first_name', 'avaliacao__avaliado__last_name', 'competencia__nome')
