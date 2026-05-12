from django.contrib.postgres.aggregates import statistics
from django.db import models
from django.conf import settings


class DataWarehouseCompras(models.Model):
    # Chaves
    filial = models.CharField(max_length=20, null=True, blank=True)
    num_sc = models.CharField(max_length=50, null=True, blank=True)
    cod_produto = models.CharField(max_length=100, null=True, blank=True)
    descricao = models.CharField(max_length=255, null=True, blank=True)

    # Projetos
    projeto_cod = models.CharField(max_length=50, null=True, blank=True)
    tarefa_cod = models.CharField(max_length=50, null=True, blank=True)

    # Pedido e Fornecedor
    num_pedido = models.CharField(max_length=50, null=True, blank=True)
    cod_fornecedor = models.CharField(max_length=50, null=True, blank=True)
    nome_fornecedor = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, null=True, blank=True)

    # Datas 
    emissao_sc = models.DateField(null=True, blank=True)
    emissao_pedido = models.DateField(null=True, blank=True)
    data_prev_recebimento_fisico = models.DateField(null=True, blank=True)
    data_recebimento_real = models.DateField(null=True, blank=True)

    # Valores e Quantidades
    qtd_solicitada = models.FloatField(default=0)
    qtd_pedido = models.FloatField(default=0)
    qtd_recebida = models.FloatField(default=0)
    valor_unitario = models.FloatField(default=0)
    valor_total = models.FloatField(default=0)

    # Métricas de SLA (Lead Times)
    leadtime_compras = models.IntegerField(default=0)
    leadtime_fornecedor = models.IntegerField(default=0)
    dias_atraso_entrega = models.IntegerField(default=0)

    # Controle de Atualização
    data_importacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "DW Compras"
        verbose_name_plural = "DW Compras"

    def __str__(self):
        return f"SC: {self.num_sc} | Pedido: {self.num_pedido} | Valor: R$ {self.valor_total}"


class OperacaoCompras(models.Model):
    # Chaves da Solicitação (SC1)
    filial = models.CharField(max_length=20, null=True, blank=True)
    num_sc = models.CharField(max_length=50, null=True, blank=True)
    item_sc = models.CharField(max_length=50, null=True, blank=True)

    # Produto e Categorização
    cod_produto = models.CharField(max_length=100, null=True, blank=True)
    descricao = models.CharField(max_length=255, null=True, blank=True)
    projeto_cod = models.CharField(max_length=50, null=True, blank=True)
    tarefa_cod = models.CharField(max_length=50, null=True, blank=True)

    # Vínculos com Pedido e Fornecedor
    num_pedidos_vinculados = models.CharField(max_length=255, null=True, blank=True)
    notas_fiscais = models.CharField(max_length=255, null=True, blank=True)
    nome_fornecedor = models.CharField(max_length=255, null=True, blank=True)

    # Status Dinâmico de Ação
    status_operacional = models.CharField(max_length=50, null=True, blank=True)

    # Datas de Acompanhamento
    emissao_sc = models.DateField(null=True, blank=True)
    emissao_ultimo_pedido = models.DateField(null=True, blank=True)
    previsao_entrega = models.DateField(null=True, blank=True)
    ultima_entrega_real = models.DateField(null=True, blank=True)

    # Quantidades
    qtd_solicitada = models.FloatField(default=0)
    qtd_pedida = models.FloatField(default=0)
    qtd_recebida = models.FloatField(default=0)
    saldo_a_comprar = models.FloatField(default=0)
    residuo = models.FloatField(default=0)

    cnpj = models.CharField('CNPJ', max_length=18, null=True, blank=True)
    tipo_produto = models.CharField('Tipo de Produto', max_length=50, null=True, blank=True)

    class Meta:
        verbose_name = "Operação de Compras"
        verbose_name_plural = "Operações de Compras"

    def __str__(self):
        return f"SC: {self.num_sc} | Status: {self.status_operacional}"


class PerguntaAvaliacao(models.Model):
    texto = models.CharField('Pergunta', max_length=255)
    ativa = models.BooleanField(default=True)
    ordem = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        return self.texto


class AvaliacaoFornecedor(models.Model):
    #coments
    num_pedido = models.CharField(max_length=50)
    cod_fornecedor = models.CharField(max_length=50)
    nome_fornecedor = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18)
    projeto = models.CharField(max_length=20)
    tipo_produto = models.CharField(max_length=50)

    avaliador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    data_avaliacao = models.DateTimeField(auto_now_add=True)

    @property
    def mediana_notas(self):
        """Media das respostas atreladas a esta avaliação especifica"""
        notas = self.respostas.values_list('nota', flat=True)
        if not notas:
            return 0
        return statistics.median(notas)

    def __str__(self):
        return f"Avaliação - Pedido: {self.num_pedido} - {self.nome_fornecedor}"


class RespostaAvaliacao(models.Model):
    #coments
    class NotaChoices(models.IntegerChoices):
        ZERO = 0, '0 - Não Atendeu'
        DEZ = 10, '10 - Atendeu Totalmente'

    avaliacao = models.ForeignKey(AvaliacaoFornecedor, on_delete=models.CASCADE, related_name='respostas')
    pergunta = models.ForeignKey(PerguntaAvaliacao, on_delete=models.PROTECT)

    nota = models.IntegerField(choices=NotaChoices.choices, default=NotaChoices.ZERO)
    justificativa = models.TextField(null=True, blank=True)