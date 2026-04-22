from django.contrib import admin
from .models import Funcionario, RegistroAbsenteismo, Vaga, Candidatura

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