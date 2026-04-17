from django.db import models

class EstruturaProduto(models.Model):
    codigo_pai = models.CharField(max_length=50, verbose_name="Código Pai")
    descricao_pai = models.CharField(max_length=255, verbose_name="Descrição Pai")
    tipo_pai = models.CharField(max_length=10, blank=True, null=True, verbose_name="Tipo Pai")
    grupo_pai = models.CharField(max_length=20, blank=True, null=True, verbose_name="Grupo Pai")
    unidade_pai = models.CharField(max_length=10, blank=True, null=True, verbose_name="Unidade Pai")
    base_estrutural = models.FloatField(default=1.0, verbose_name="Base Estrutural")

    nivel = models.CharField(max_length=10, verbose_name="Nível")
    codigo_componente = models.CharField(max_length=50, verbose_name="Código Componente")
    descricao_componente = models.CharField(max_length=255, verbose_name="Descrição Componente")
    tipo_componente = models.CharField(max_length=10, blank=True, null=True, verbose_name="Tipo Componente")
    grupo_componente = models.CharField(max_length=20, blank=True, null=True, verbose_name="Grupo Componente")
    unidade_medida_filho = models.CharField(max_length=10, blank=True, null=True, verbose_name="UM Componente")

    quantidade_necessaria = models.FloatField(default=0.0, verbose_name="Qtd Necessária")
    quantidade = models.FloatField(default=0.0, verbose_name="Quantidade")
    perda_percentual = models.FloatField(default=0.0, verbose_name="Perda %")
    tipo_quantidade = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tipo Quantidade")

    inicio_validade = models.DateField(blank=True, null=True, verbose_name="Ini. Validade")
    fim_validade = models.DateField(blank=True, null=True, verbose_name="Fim Validade")
    data_importacao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Importação")

    class Meta:
        verbose_name = "Estrutura Simples"
        verbose_name_plural = "Estruturas Simples"

    def __str__(self):
        return f"{self.codigo_pai} -> {self.codigo_componente} (Qtd: {self.quantidade_necessaria})"