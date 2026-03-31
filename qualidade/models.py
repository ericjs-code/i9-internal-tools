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


class RNC(models.Model):
    # Enums (Choices) para campos de regra de negócio imutável
    class DetectorChoices(models.TextChoices):
        CLIENTE = 'CL', 'Cliente'
        INTERNO = 'IN', 'Interno'
        AUD_INT = 'AI', 'Auditor Interno'
        AUD_EXT = 'AE', 'Auditor Externo'
        FORNECEDOR = 'FO', 'Fornecedor'

    class CategoriaChoices(models.TextChoices):
        COMERCIAL = 'CO', 'Comercial'
        ENGENHARIA = 'EN', 'Engenharia'
        PCP = 'PC', 'PCP'
        FABRICACAO = 'FA', 'Fabricação'
        MONTAGEM = 'MO', 'Montagem'
        SUPRIMENTOS = 'SU', 'Suprimentos'
        FORNECEDOR = 'FO', 'Fornecedor'
        EXPEDICAO = 'EX', 'Expedição'
        QUALIDADE = 'QU', 'Qualidade'
        RH = 'RH', 'Recursos Humanos'
        FINANCEIRO = 'FI', 'Financeiro'
        SGQ = 'SG', 'SGQ'

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

    class Origem(models.TextChoices):
        COMERCIAL = 'CO', 'Comercial'
        PROJETO_ENGENHARIA  = 'PE', 'Projeto_Engenharia'
        FABRICACAO = 'FA', 'Fabricação'
        MONTAGEM_COMISSIONAMENTO = 'MC', 'Montagem_comissionamento'
        SUPRIMENTOS = 'SU', 'Suprimentos'
        RH = 'RH', 'RH'
        FORNECEDOR = 'FO', 'Fornecedor'
        SGQ = 'SG', 'Processo_interno_SGQ'


    # --- Identificação e Origem ---
    registrador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='rncs_registradas', verbose_name='Registrado por')
    data_abertura = models.DateField('Data de Abertura', auto_now_add=True)
    projeto_cod = models.CharField('Código do Projeto', max_length=50, blank=True, null=True)
    elemento_rastreador = models.CharField('Elemento Rastreador', max_length=100, blank=True, null=True)

    # --- Classificações Base (Choices) ---
    detector = models.CharField('Detector', max_length=2, choices=DetectorChoices.choices)
    categoria = models.CharField('Categoria da NC', max_length=2, choices=CategoriaChoices.choices, default=CategoriaChoices.COMERCIAL)
    criticidade = models.CharField('Nível de Criticidade', max_length=1, choices=CriticidadeChoices.choices)
    status = models.CharField('Status', max_length=2, choices=StatusChoices.choices, default=StatusChoices.PRELIMINAR)
    origem = models.CharField('Origem', max_length=2, choices=Origem.choices, default=Origem.COMERCIAL)

    # --- Relacionamentos de Domínio (ForeignKeys) ---
    equipamento = models.ForeignKey(Equipamento, on_delete=models.PROTECT, verbose_name='Equipamento', blank=True, null=True)
    local = models.ForeignKey(Local, on_delete=models.PROTECT, verbose_name='Local')

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


class RNCImagem(models.Model):
    rnc = models.ForeignKey(RNC, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField('Anexo de Imagem', upload_to='qualidade/rnc/imagens/')
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imagem da RNC'
        verbose_name_plural = 'Imagens da RNC'

class RNCEficaciaImagem(models.Model):
    rnc = models.ForeignKey(RNC, on_delete=models.CASCADE, related_name='eficacia_imagens')
    imagens_eficacia = models.ImageField('Anexo de Imagem Eficacia', upload_to='qualidade/rnc/eficacia')
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imagem Eficacia da RNC'
        verbose_name_plural = 'Imagens da Eficacia das RNCs'

    def __str__(self):
        return f"Anexo da RNC #{self.rnc.id}"