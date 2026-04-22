from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import uuid
import os


def validar_curriculo(value):
    """Validador de Model para garantir que o ficheiro tem no maximo 3MB e é tipo pdf ou word"""
    limite_mb = 3
    limite_maximo = limite_mb * 1024 * 1024

    if value.size > limite_maximo:
        raise ValidationError(f"Tamanho do arquivo excede o limite máximo de {limite_mb} MB.")
    extensao = os.path.splitext(value.name)[1].lower()
    extensoes = ['.pdf', '.doc', '.docx']

    if extensao not in extensoes:
        raise ValidationError('Por questões de segurança, envie apenas currículos em PDF ou Word.')


class Vaga(models.Model):

    class SETORES(models.TextChoices):
        COMERCIAL = 'CA', 'Comercial'
        COMPRAS = 'CO', 'Compras'
        DIRETORIA = 'DI', 'Diretoria'
        FINANCEIRO = 'FI', 'Financeiro'
        OBRA = 'OB', 'Obra'
        QUALIDADE = 'QA', 'SGQ'
        FABRICA = 'FA', 'Fabrica'
        PROJETOS = 'PR', 'Projetos'
        ENGENHARIA = 'EG', 'Engenharia'
        RH = 'RH', 'Recursos Humanos'
        TI = 'TI', 'T.I'

    titulo = models.CharField(max_length=150, verbose_name="Título da Vaga")
    setor = models.CharField(max_length=2, choices=SETORES.choices, verbose_name="Setor")
    descricao = models.TextField(verbose_name="Descrição das Atividades")
    requisitos = models.TextField(verbose_name="Requisitos e Qualificações")
    ativa = models.BooleanField(default=True, verbose_name="Vaga Aberta (Aceitando currículos)")
    data_criacao = models.DateTimeField(auto_now_add=True)
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='vagas_criadas')
    solicitacao_origem = models.OneToOneField('SolicitacaoVaga', on_delete=models.SET_NULL, null=True, blank=True, related_name='vaga_gerada')

    def __str__(self):
        status = "Aberta" if self.ativa else "Fechada"
        return f"{self.titulo} - {self.get_setor_display()} ({status})"


class Candidatura(models.Model):
    class STATUS(models.TextChoices):
        NOVO = 'NO', 'Novo (Aguardando Triagem)'
        EM_ANALISE = 'EA', 'Em Análise'
        ENTREVISTA = 'ET', 'Em Fase de Entrevista'
        APROVADO = 'AP', 'Aprovado (Contratado)'
        REPROVADO = 'RE', 'Reprovado / Banco de Talentos'

    vaga = models.ForeignKey(Vaga, on_delete=models.PROTECT, related_name='candidaturas')
    nome_completo = models.CharField(max_length=150)
    email = models.EmailField()
    telefone = models.CharField(max_length=20, verbose_name="WhatsApp / Telefone")
    linkedin = models.URLField(blank=True, null=True, verbose_name="Perfil do LinkedIn")

    curriculo = models.FileField(
        upload_to='curriculos/%Y/%m',
        verbose_name='Currículo (PDF)',
        validators = [validar_curriculo]
    )

    status = models.CharField(max_length=2, choices=STATUS.choices, default=STATUS.NOVO)
    observacoes_rh = models.TextField(blank=True, verbose_name="Anotações Internas do RH")
    data_aplicacao = models.DateTimeField(auto_now_add=True)

    lgpd_consentimento = models.BooleanField(default=False, verbose_name="LGPD (Consentimento)")

    def __str__(self):
        return f"{self.nome_completo} - {self.vaga.titulo}"


class SolicitacaoVaga(models.Model):
    MOTIVOS = [
        ('AUMENTO_FUNC', 'Aumento de quadro - Funcionário'),
        ('AUMENTO_ESTAG', 'Aumento de quadro - Estagiário'),
        ('SUBST_DEMITIDO', 'Substituição - Demitido'),
        ('SUBST_PEDIDO', 'Substituição - Pedido de demissão'),
        ('TEMP_AFASTAMENTO', 'Temporário - Afastamento'),
    ]

    SEXO = [
        ('INDIFERENTE', 'Indiferente / Qualquer'),
        ('MASCULINO', 'Masculino'),
        ('FEMININO', 'Feminino'),
    ]

    ESCOLARIDADE = [
        ('FUNDAMENTAL', 'Ensino Fundamental Completo'),
        ('MEDIO', 'Ensino Médio Completo'),
        ('TECNICO', 'Curso Técnico'),
        ('SUP_CURSANDO', 'Superior Cursando'),
        ('SUP_COMPLETO', 'Superior Completo'),
    ]

    STATUS_APROVACAO = [
        ('PENDENTE', 'Aguardando Aprovação do RH'),
        ('APROVADA', 'Aprovada (Vaga Aberta)'),
        ('REPROVADA', 'Reprovada / Cancelada'),
    ]

    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='solicitacoes_vagas')
    cargo_solicitante = models.CharField(max_length=100, verbose_name="Seu Cargo Atual")
    data_solicitacao = models.DateTimeField(auto_now_add=True)

    departamento = models.CharField(max_length=2, choices=Vaga.SETORES.choices)  # Reutilizando os setores da classe Vaga
    nome_vaga = models.CharField(max_length=150, verbose_name="Nome da Vaga")
    quantidade_vagas = models.PositiveIntegerField(default=1)
    data_prevista_inicio = models.DateField(verbose_name="Data Prevista para Início")

    motivo = models.CharField(max_length=20, choices=MOTIVOS)
    nome_substituido = models.CharField(max_length=150, blank=True, null=True,
                                        verbose_name="Nome do Substituído (Se houver)")

    descricao_atividades = models.TextField(verbose_name="Descrição Sumária das Atividades")
    sexo = models.CharField(max_length=15, choices=SEXO, default='INDIFERENTE')
    escolaridade = models.CharField(max_length=20, choices=ESCOLARIDADE)
    curso_area = models.CharField(max_length=150, blank=True, null=True, verbose_name="Curso e/ou Área")
    conhecimentos_desejaveis = models.TextField(verbose_name="Conhecimentos e/ou experiências")
    atitudes_desejaveis = models.TextField(verbose_name="Atitudes desejáveis")
    observacoes_gerais = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_APROVACAO, default='PENDENTE')
    observacoes_rh = models.TextField(blank=True, null=True, verbose_name="Parecer do RH")

    def __str__(self):
        return f"Solicitação: {self.nome_vaga} - {self.solicitante.username}"


class PesquisaDemissional(models.Model):
    TIPO_DEMISSAO_CHOICES = [
        ('VOLUNTARIA', 'Pedido de Demissão (Iniciativa do Colaborador)'),
        ('INVOLUNTARIA', 'Demissão sem Justa Causa (Iniciativa da Empresa)'),
        ('JUSTA_CAUSA', 'Demissão por Justa Causa'),
        ('ACORDO', 'Acordo entre as partes'),
    ]

    id_pesquisa = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gerada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pesquisas_geradas')
    data_geracao = models.DateTimeField(auto_now_add=True)
    respondida = models.BooleanField(default=False, verbose_name="Pesquisa já foi respondida?")
    data_resposta = models.DateTimeField(null=True, blank=True)

    ex_funcionario_nome = models.CharField(max_length=150, verbose_name="Nome do Ex-Colaborador")
    setor = models.CharField(max_length=2, choices=Vaga.SETORES.choices)
    tipo_demissao = models.CharField(max_length=50, choices=TIPO_DEMISSAO_CHOICES)
    periodo_saida = models.CharField(max_length=50, verbose_name="Mês/Ano de Saída")
    tempo_casa = models.CharField(max_length=50, verbose_name="Tempo de Casa")

    motivo_saida = models.CharField(max_length=150, blank=True, null=True, verbose_name="Motivo Principal da Saída")
    diferente = models.TextField(blank=True, null=True, verbose_name="O que poderia ter sido feito diferente?")

    nota_lideranca = models.IntegerField(blank=True, null=True, verbose_name="Nota - Liderança")
    nota_oportunidade = models.IntegerField(blank=True, null=True, verbose_name="Nota - Oportunidades")
    nota_reconhecimento = models.IntegerField(blank=True, null=True, verbose_name="Nota - Reconhecimento")
    nota_clima = models.IntegerField(blank=True, null=True, verbose_name="Nota - Clima Organizacional")
    nota_recomendacao = models.IntegerField(blank=True, null=True, verbose_name="Nota - Recomendação da Empresa (eNPS)")

    def __str__(self):
        status = 'Respondida' if self.respondida else 'Pendente'
        return f'{self.ex_funcionario_nome} - {self.get_setor_display()}({status})'

    def get_link_externo(self):
        from django.urls import reverse
        return reverse('responder_pesquisa', kwargs={'uuid_pesquisa': self.id_pesquisa})


class Funcionario(models.Model):
    class SITUACAO(models.TextChoices):
        ATIVO = 'AT', 'Trabalhando'
        DEMITIDO = 'DM', 'Demitido'

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='perfil_funcionario',
    )

    nome_completo = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, unique=True, verbose_name="CPF")
    data_nascimento = models.DateField(null=True, blank=True)

    data_admissao = models.DateField()
    data_demissao = models.DateField(null=True, blank=True)
    cargo = models.CharField(max_length=100)
    salario = models.DecimalField(max_digits=10, decimal_places=2)
    situacao = models.CharField(max_length=2, choices=SITUACAO.choices, default=SITUACAO.ATIVO)

    setor = models.CharField(max_length=2, choices=Vaga.SETORES.choices)

    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    matricula = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def __str__(self):
        status = "Ativo" if self.situacao == "AT" else "Desligado"
        return f'{self.nome_completo} - {self.get_setor_display()} - ({status})'

    def save(self, *args, **kwargs):
        if self.cpf:
            import re
            self.cpf = re.sub(r'\D', '', self.cpf)
        super().save(*args, **kwargs)


class RegistroAbsenteismo(models.Model):
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='registros_ponto'
    )

    data_referencia = models.DateField()

    horas_normais = models.DurationField(null=True, blank=True)
    horas_falta = models.DurationField(null=True, blank=True)
    horas_extras = models.DurationField(null=True, blank=True)
    abono = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ['funcionario', 'data_referencia']

    def __str__(self):
        return f'Ponto: {self.funcionario.nome_completo} - {self.data_referencia.strftime("%m/%Y")}'

