from django.db import models

class TipoMovimentacao(models.TextChoices):
    ENTRADA = 'ENTRADA', 'Entrada'
    SAIDA = 'SAIDA', 'Saída'

class OrigemMovimentacao(models.TextChoices):
    NF_ENTRADA = 'NF_ENTRADA', 'Nota Fiscal de Entrada'
    NF_SAIDA = 'NF_SAIDA', 'Nota Fiscal de Saída'
    MOV_INTERNA = 'MOV_INTERNA', 'Movimentação Interna'

class MovimentacaoEstoquePCP(models.Model):
    produto_codigo = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Código do Produto"
    )
    data_movimentacao = models.DateField(
        db_index=True,
        verbose_name="Data da Movimentação"
    )
    tipo_movimentacao = models.CharField(
        max_length=10,
        choices=TipoMovimentacao.choices,
        verbose_name="Tipo de Movimentação"
    )
    origem_movimentacao = models.CharField(
        max_length=20,
        choices=OrigemMovimentacao.choices,
        verbose_name="Origem da Movimentação"
    )
    quantidade = models.DecimalField(
        max_digits=19,
        decimal_places=5,
        verbose_name="Quantidade"
    )
    documento = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Documento de Origem"
    )
    # Campo chave para identificar a natureza da movimentação interna (SD3)
    cf_operacao = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        verbose_name="CF da Operação (SD3)"
    )
    # Timestamps para rastreabilidade do ETL
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Movimentação de Estoque (PCP)"
        verbose_name_plural = "Movimentações de Estoque (PCP)"
        # Constraint para garantir a unicidade do registro, chave para o UPSERT.
        unique_together = [
            ['produto_codigo', 'data_movimentacao', 'documento', 'origem_movimentacao', 'cf_operacao']
        ]
        # Índice composto para otimizar a query principal do Power BI (filtrando por produto e data)
        indexes = [
            models.Index(fields=['produto_codigo', 'data_movimentacao']),
        ]
