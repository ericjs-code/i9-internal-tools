from django.db import models


class DataWarehouseCompras(models.Model):
    # Chaves e Identificadores
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

    # Datas (Mantidas como CharField para evitar erro com o "-" gerado no seu ETL)
    emissao_sc = models.CharField(max_length=20, null=True, blank=True)
    emissao_pedido = models.CharField(max_length=20, null=True, blank=True)
    data_prev_recebimento_fisico = models.CharField(max_length=20, null=True, blank=True)
    data_recebimento_real = models.CharField(max_length=20, null=True, blank=True)

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