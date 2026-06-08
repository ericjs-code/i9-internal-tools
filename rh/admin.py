from django.contrib import admin
from .models import (Funcionario, RegistroAbsenteismo, Vaga, Candidatura,
                     FormularioAdmissional, DependenteAdmissional)

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
    list_display = ('nome_completo', 'cpf', 'matricula', 'get_setor_display', 'get_situacao_display')
    # Cria uma barra de pesquisa por nome, cpf ou matrícula
    search_fields = ('nome_completo', 'cpf', 'matricula')
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
