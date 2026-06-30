from django.db import models
from django.conf import settings


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


class PmsProjeto(models.Model):
    filial = models.CharField(max_length=20)
    projeto = models.CharField(max_length=50)
    revisao = models.CharField(max_length=20)
    descricao = models.CharField(max_length=255, blank=True, default='')
    data_base = models.DateField(null=True, blank=True)
    calendario = models.CharField(max_length=50, blank=True, default='')
    mascara = models.CharField(max_length=50, blank=True, default='')
    delimitador = models.CharField(max_length=10, blank=True, default='')
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Projeto PMS"
        verbose_name_plural = "Projetos PMS"
        constraints = [
            models.UniqueConstraint(
                fields=['filial', 'projeto', 'revisao'],
                name='uniq_pms_projeto_revisao',
            )
        ]
        indexes = [
            models.Index(fields=['projeto', 'revisao']),
            models.Index(fields=['filial', 'projeto', 'revisao']),
        ]

    def __str__(self):
        return f"{self.projeto} | Rev. {self.revisao}"


class PmsEdt(models.Model):
    filial = models.CharField(max_length=20)
    projeto = models.CharField(max_length=50)
    revisao = models.CharField(max_length=20)
    edt = models.CharField(max_length=50)
    edt_pai = models.CharField(max_length=50, blank=True, default='')
    descricao = models.CharField(max_length=255, blank=True, default='')
    nivel = models.PositiveIntegerField(null=True, blank=True)
    ordem = models.CharField(max_length=50, blank=True, default='')
    unidade = models.CharField(max_length=20, blank=True, default='')
    quantidade = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_previsto = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EDT PMS"
        verbose_name_plural = "EDTs PMS"
        constraints = [
            models.UniqueConstraint(
                fields=['filial', 'projeto', 'revisao', 'edt'],
                name='uniq_pms_edt_revisao',
            )
        ]
        indexes = [
            models.Index(fields=['projeto', 'revisao', 'edt']),
            models.Index(fields=['filial', 'projeto', 'revisao', 'edt_pai']),
        ]

    def __str__(self):
        return f"{self.projeto} | {self.edt}"


class PmsTarefa(models.Model):
    filial = models.CharField(max_length=20)
    projeto = models.CharField(max_length=50)
    revisao = models.CharField(max_length=20)
    tarefa = models.CharField(max_length=50)
    edt = models.CharField(max_length=50, blank=True, default='')
    descricao = models.CharField(max_length=255, blank=True, default='')
    nivel = models.PositiveIntegerField(null=True, blank=True)
    ordem = models.CharField(max_length=50, blank=True, default='')
    unidade = models.CharField(max_length=20, blank=True, default='')
    quantidade = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    data_inicio_prevista = models.DateField(null=True, blank=True)
    data_fim_prevista = models.DateField(null=True, blank=True)
    custo_previsto = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tarefa PMS"
        verbose_name_plural = "Tarefas PMS"
        constraints = [
            models.UniqueConstraint(
                fields=['filial', 'projeto', 'revisao', 'tarefa'],
                name='uniq_pms_tarefa_revisao',
            )
        ]
        indexes = [
            models.Index(fields=['projeto', 'revisao', 'tarefa']),
            models.Index(fields=['filial', 'projeto', 'revisao', 'edt']),
        ]

    def __str__(self):
        return f"{self.projeto} | {self.tarefa}"


class PmsCustoTarefa(models.Model):
    filial = models.CharField(max_length=20)
    projeto = models.CharField(max_length=50)
    revisao = models.CharField(max_length=20)
    edt = models.CharField(max_length=50, blank=True, default='')
    tarefa = models.CharField(max_length=50)
    custo_previsto = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_previsto_produtos = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_previsto_despesas = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_previsto_detalhado = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_realizado = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    custo_empenhado = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    saldo_previsto_realizado = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    variacao_percentual = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Custo PMS por Tarefa"
        verbose_name_plural = "Custos PMS por Tarefa"
        constraints = [
            models.UniqueConstraint(
                fields=['filial', 'projeto', 'revisao', 'tarefa'],
                name='uniq_pms_custo_tarefa_revisao',
            )
        ]
        indexes = [
            models.Index(fields=['projeto', 'revisao', 'tarefa']),
            models.Index(fields=['filial', 'projeto', 'revisao', 'edt']),
        ]

    def __str__(self):
        return f"{self.projeto} | {self.tarefa} | R$ {self.custo_previsto}"


class ComprasSyncLog(models.Model):
    STATUS_SUCESSO = 'SUCESSO'
    STATUS_ERRO = 'ERRO'
    STATUS_PROCESSANDO = 'PROCESSANDO'

    STATUS_CHOICES = [
        (STATUS_PROCESSANDO, 'Processando'),
        (STATUS_SUCESSO, 'Sucesso'),
        (STATUS_ERRO, 'Erro'),
    ]

    nome = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROCESSANDO)
    iniciado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    arquivos_processados = models.JSONField(default=list, blank=True)
    linhas_lidas = models.PositiveIntegerField(default=0)
    linhas_gravadas = models.PositiveIntegerField(default=0)
    mensagem = models.TextField(blank=True, default='')
    erro = models.TextField(blank=True, default='')
    executado_por = models.CharField(max_length=150, blank=True, default='')

    class Meta:
        verbose_name = "Log de Sincronização de Compras"
        verbose_name_plural = "Logs de Sincronização de Compras"
        ordering = ['-iniciado_em']
        indexes = [
            models.Index(fields=['nome', 'status']),
            models.Index(fields=['-iniciado_em']),
        ]

    def __str__(self):
        return f"{self.nome} | {self.status} | {self.iniciado_em:%d/%m/%Y %H:%M}"


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
        return sum(notas) / len(notas)

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
