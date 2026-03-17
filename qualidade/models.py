from django.db import models
from django.conf import settings


class Equipamento(models.Model):
    nome = models.CharField('Nome do Equipamento', max_length=100, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Equipamento'
        verbose_name_plural = 'Equipamentos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Local(models.Model):
    nome = models.CharField('Local/Setor', max_length=100, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Local'
        verbose_name_plural = 'Locais'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class TipoNC(models.Model):
    nome = models.CharField('Tipo de Não Conformidade', max_length=100, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tipo de NC'
        verbose_name_plural = 'Tipos de NC'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class RNC(models.Model):
    # Enums (Choices) para campos de regra de negócio imutável
    class DetectorChoices(models.TextChoices):
        CLIENTE = 'CL', 'Cliente'
        INTERNO = 'IN', 'Interno'
        AUD_INT = 'AI', 'Auditor Interno'
        AUD_EXT = 'AE', 'Auditor Externo'
        FORNECEDOR = 'FO', 'Fornecedor'

    class ClassificacaoChoices(models.TextChoices):
        SISTEMA = 'SI', 'Sistema'
        PRODUTO = 'PR', 'Produto'
        PROCESSO = 'PO', 'Processo'

    class CriticidadeChoices(models.TextChoices):
        ALTO = 'A', 'Alto'
        MEDIO = 'M', 'Médio'
        BAIXO = 'B', 'Baixo'

    class StatusChoices(models.TextChoices):
        NAO_INICIADA = 'NI', 'Não iniciada'
        EM_ANDAMENTO = 'EA', 'Em andamento'
        CONCLUIDO = 'CO', 'Concluído'
        FORA_TRILHOS = 'FT', 'Fora dos trilhos'
        PRELIMINAR = 'PR', 'Registro preliminar'
        CANCELADO = 'CA', 'Cancelado'

    # --- Identificação e Origem ---
    registrador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='rncs_registradas', verbose_name='Registrado por')
    data_abertura = models.DateField('Data de Abertura', auto_now_add=True)
    projeto_cod = models.CharField('Código do Projeto', max_length=50, blank=True, null=True)
    elemento_rastreador = models.CharField('Elemento Rastreador', max_length=100, blank=True, null=True)

    # --- Classificações Base (Choices) ---
    detector = models.CharField('Detector', max_length=2, choices=DetectorChoices.choices)
    classificacao = models.CharField('Classificação da NC', max_length=2, choices=ClassificacaoChoices.choices)
    criticidade = models.CharField('Nível de Criticidade', max_length=1, choices=CriticidadeChoices.choices)
    justificativa_criticidade = models.TextField('Justificativa da Criticidade', blank=True, null=True)
    status = models.CharField('Status', max_length=2, choices=StatusChoices.choices, default=StatusChoices.PRELIMINAR)

    # --- Relacionamentos de Domínio (ForeignKeys) ---
    equipamento = models.ForeignKey(Equipamento, on_delete=models.PROTECT, verbose_name='Equipamento', blank=True, null=True)
    local = models.ForeignKey(Local, on_delete=models.PROTECT, verbose_name='Local')
    tipo_nc = models.ForeignKey(TipoNC, on_delete=models.PROTECT, verbose_name='Tipo de NC')

    # --- Textos Analíticos e Ações ---
    descricao = models.TextField('Descrição da Não Conformidade')
    correcao = models.TextField('Correção Imediata', blank=True, null=True)
    ishikawa_link = models.URLField('Diagrama Ishikawa (Link)', blank=True, null=True)
    causas_principais = models.TextField('Principais Causas', blank=True, null=True)
    acao_corretiva = models.TextField('Ação Corretiva', blank=True, null=True)

    # --- Verificação de Eficácia ---
    eficacia_texto = models.TextField('Verificação de Eficácia (Texto)', blank=True, null=True)
    eficacia_pdf = models.FileField('Mídia da Verificação (PDF)', upload_to='qualidade/rnc/pdfs/', blank=True, null=True)

    # --- Gestão de Prazos e Responsáveis ---
    # ManyToMany permite vincular N usuários como responsáveis por uma única RNC
    responsaveis = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='rncs_responsaveis', blank=True, verbose_name='Responsáveis')
    data_prevista_conclusao = models.DateField('Data Prevista de Conclusão', blank=True, null=True)
    data_encerramento = models.DateField('Data de Encerramento', blank=True, null=True)

    # --- Controle de Concorrência e Auditoria ---
    versao = models.IntegerField('Versão do Registro', default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registro de Não Conformidade'
        verbose_name_plural = 'Registros de Não Conformidade'
        ordering = ['-id']

    def __str__(self):
        return f"RNC #{self.id} - {self.get_status_display()}"