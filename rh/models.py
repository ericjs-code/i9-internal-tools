from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from phonenumber_field.modelfields import PhoneNumberField
from .constants import ORGAOS_EXPEDIDORES_RG, UF_CHOICES
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


SIM_NAO_CHOICES = [
    ('SIM', 'Sim'),
    ('NAO', 'Nao'),
]


class FormularioAdmissional(models.Model):
    COR_RACA_CHOICES = [
        ('BRANCA', 'Branca'),
        ('PRETA', 'Preta'),
        ('PARDA', 'Parda'),
        ('AMARELA', 'Amarela'),
        ('INDIGENA', 'Indigena'),
        ('NAO_INFORMAR', 'Prefiro nao informar'),
    ]

    GRAU_INSTRUCAO_CHOICES = [
        ('FUND_INCOMPLETO', 'Ensino Fundamental Incompleto'),
        ('FUND_COMPLETO', 'Ensino Fundamental Completo'),
        ('MEDIO_INCOMPLETO', 'Ensino Medio Incompleto'),
        ('MEDIO_COMPLETO', 'Ensino Medio Completo'),
        ('SUPERIOR_INCOMPLETO', 'Ensino Superior Incompleto'),
        ('SUPERIOR_COMPLETO', 'Ensino Superior Completo'),
        ('POS_GRADUACAO', 'Pos-graduacao'),
        ('MESTRADO', 'Mestrado'),
        ('DOUTORADO', 'Doutorado'),
    ]

    ESTADO_CIVIL_CHOICES = [
        ('SOLTEIRO', 'Solteiro(a)'),
        ('CASADO', 'Casado(a)'),
        ('UNIAO_ESTAVEL', 'Uniao Estavel'),
        ('DIVORCIADO', 'Divorciado(a)'),
        ('SEPARADO', 'Separado(a)'),
        ('VIUVO', 'Viuvo(a)'),
    ]

    BOTINA_CHOICES = [(str(tamanho), str(tamanho)) for tamanho in range(34, 47)]
    CAMISA_CHOICES = [('PP', 'PP'), ('P', 'P'), ('M', 'M'), ('G', 'G'), ('GG', 'GG'), ('XG', 'XG'), ('XXG', 'XXG')]
    CALCA_CHOICES = CAMISA_CHOICES + [(str(tamanho), str(tamanho)) for tamanho in range(36, 55, 2)]

    id_formulario = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gerado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='formularios_admissionais_gerados')
    data_geracao = models.DateTimeField(auto_now_add=True)
    respondido = models.BooleanField(default=False, verbose_name="Formulario ja foi respondido?")
    data_resposta = models.DateTimeField(null=True, blank=True)
    candidato_nome_interno = models.CharField(max_length=150, verbose_name="Nome completo do futuro colaborador")
    observacoes_rh = models.TextField(blank=True, null=True)

    nome_completo = models.CharField(max_length=150, blank=True, null=True)
    cpf = models.CharField(max_length=14, blank=True, null=True)
    cidade_estado = models.CharField(max_length=120, blank=True, null=True, help_text="Ex.: Araucaria-PR")
    funcao_pretendida = models.CharField(max_length=120, blank=True, null=True)

    pis = models.CharField(max_length=30, blank=True, null=True)
    numero_ctps = models.CharField(max_length=30, blank=True, null=True)
    serie_ctps = models.CharField(max_length=4, blank=True, null=True)
    uf_ctps = models.CharField(max_length=2, choices=UF_CHOICES, blank=True, null=True)

    cep = models.CharField(max_length=10, blank=True, null=True, help_text="Ex.: 00000000")
    endereco = models.CharField(max_length=255, blank=True, null=True, help_text="Rua e numero")
    bairro = models.CharField(max_length=120, blank=True, null=True)

    telefone_principal = PhoneNumberField(region='BR', blank=True, null=True, help_text="Ex.: DD 99999-9999")
    contato_recado = PhoneNumberField(region='BR', blank=True, null=True, help_text="Ex.: DD 99999-9999")
    email = models.EmailField(blank=True, null=True)

    data_nascimento = models.DateField(blank=True, null=True)
    estado_nascimento = models.CharField(max_length=2, choices=UF_CHOICES, blank=True, null=True)
    naturalidade = models.CharField(max_length=120, blank=True, null=True, help_text="Cidade onde nasceu")
    cor_raca = models.CharField(max_length=20, choices=COR_RACA_CHOICES, blank=True, null=True)
    grau_instrucao = models.CharField(max_length=30, choices=GRAU_INSTRUCAO_CHOICES, blank=True, null=True)
    nome_mae = models.CharField(max_length=150, blank=True, null=True)
    nome_pai = models.CharField(max_length=150, blank=True, null=True)

    numero_rg = models.CharField(max_length=30, blank=True, null=True)
    orgao_expedidor = models.CharField(max_length=30, choices=ORGAOS_EXPEDIDORES_RG, blank=True, null=True)
    uf_rg = models.CharField(max_length=2, choices=UF_CHOICES, blank=True, null=True)
    data_emissao_rg = models.DateField(blank=True, null=True)
    titulo_eleitor = models.CharField(max_length=30, blank=True, null=True)
    zona_eleitoral = models.CharField(max_length=20, blank=True, null=True)
    secao_eleitoral = models.CharField(max_length=20, blank=True, null=True)
    uf_titulo_eleitor = models.CharField(max_length=2, choices=UF_CHOICES, blank=True, null=True)
    reservista = models.CharField(max_length=50, blank=True, null=True)
    cnh = models.CharField(max_length=100, blank=True, null=True, help_text="Informar numero, validade e estado")
    numero_cnh = models.CharField(max_length=9, blank=True, null=True)
    validade_cnh = models.DateField(blank=True, null=True)
    estado_cnh = models.CharField(max_length=2, choices=UF_CHOICES, blank=True, null=True)

    estado_civil = models.CharField(max_length=20, choices=ESTADO_CIVIL_CHOICES, blank=True, null=True)
    possui_dependentes_ir = models.CharField(max_length=3, choices=SIM_NAO_CHOICES, blank=True, null=True)

    botina = models.CharField(max_length=2, choices=BOTINA_CHOICES, blank=True, null=True)
    camisa = models.CharField(max_length=3, choices=CAMISA_CHOICES, blank=True, null=True)
    calca = models.CharField(max_length=3, choices=CALCA_CHOICES, blank=True, null=True)

    utiliza_vale_transporte = models.CharField(max_length=3, choices=SIM_NAO_CHOICES, blank=True, null=True)
    trajeto_vale_transporte = models.TextField(blank=True, null=True)
    lgpd_consentimento = models.BooleanField(default=False)

    def __str__(self):
        status = 'Respondido' if self.respondido else 'Pendente'
        return f'{self.candidato_nome_interno} ({status})'

    def get_link_externo(self):
        from django.urls import reverse
        return reverse('responder_formulario_admissional', kwargs={'uuid_formulario': self.id_formulario})

    def save(self, *args, **kwargs):
        import re
        if self.cpf:
            self.cpf = re.sub(r'\D', '', self.cpf)
        if self.cep:
            self.cep = re.sub(r'\D', '', self.cep)
        for campo in ['pis', 'numero_ctps', 'serie_ctps', 'numero_rg', 'titulo_eleitor', 'numero_cnh']:
            valor = getattr(self, campo, None)
            if valor:
                setattr(self, campo, re.sub(r'\D', '', valor))
        super().save(*args, **kwargs)


class DependenteAdmissional(models.Model):
    formulario = models.ForeignKey(FormularioAdmissional, related_name='dependentes', on_delete=models.CASCADE)
    nome_completo = models.CharField(max_length=150)
    data_nascimento = models.DateField()
    rg = models.CharField(max_length=30)
    cpf = models.CharField(max_length=14)
    cidade_estado_nascimento = models.CharField(max_length=120)

    def __str__(self):
        return f'{self.nome_completo} - {self.formulario.candidato_nome_interno}'

    def save(self, *args, **kwargs):
        import re
        if self.cpf:
            self.cpf = re.sub(r'\D', '', self.cpf)
        super().save(*args, **kwargs)


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

