from django.contrib import admin
from .models import PerguntaAvaliacao, AvaliacaoFornecedor, RespostaAvaliacao

@admin.register(PerguntaAvaliacao)
class PerguntaAvaliacaoAdmin(admin.ModelAdmin):
    list_display = ('texto', 'ativa', 'ordem')
    list_editable = ('ativa', 'ordem')
    ordering = ('ordem',)

admin.site.register(AvaliacaoFornecedor)
admin.site.register(RespostaAvaliacao)