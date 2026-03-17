from django.db import models
from django.conf import settings


class STO(models.Model):
    OPCOES_SNO = [
        ('SIM', 'Sim'),
        ('NAO', 'Não'),
        ('OUTROS', 'Outros')
    ]

    OPCOES_FRETE = [
        ('CIF', 'CIF'),
        ('FOB', 'FOB'),
        ('OUTROS', 'Outros')
    ]

    OPCOES_SIM_NAO = [
        ('SIM', 'Sim'),
        ('NAO','Não')
    ]

    consultor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='stos_criadas')
    cliente = models.CharField(max_length=200)
    cidade = models.CharField(max_length=150)
    contato = models.CharField(max_length=150, verbose_name="Contato (Nome/Telefone)")
    atividade = models.CharField(max_length=150)
    codigo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Código da STO")
    data = models.DateField(auto_now_add=True)
    email = models.EmailField()


    orc_obras = models.BooleanField(default=False, verbose_name="Obras")
    orc_engenharia = models.BooleanField(default=False, verbose_name="Engenharia")
    orc_equipamentos = models.BooleanField(default=False, verbose_name="Equipamentos")
    orc_locacoes = models.BooleanField(default=False, verbose_name="Locações")
    orc_manutencoes = models.BooleanField(default=False, verbose_name="Manutenções")
    orc_outros = models.CharField(max_length=150, blank=True, null=True, verbose_name="Outro Tipo de Orçamento")


    data_prevista = models.DateField(blank=True, null=True)
    local_atividade = models.CharField(max_length=200)
    capacidade_fabrica = models.CharField(max_length=100, verbose_name="Capacidade Fábrica (T/h)")
    produto = models.CharField(max_length=150)
    densidade = models.CharField(max_length=100, blank=True, null=True)
    granulometria = models.CharField(max_length=100, blank=True, null=True)
    umidade = models.CharField(max_length=100, blank=True, null=True)


    tipo_frete = models.CharField(max_length=10, choices=OPCOES_FRETE, default='CIF')
    tipo_frete_outros = models.CharField(max_length=150, blank=True, null=True)

    eletrica_automacao = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    eletrica_automacao_outros = models.CharField(max_length=150, blank=True, null=True)

    civil = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    civil_outros = models.CharField(max_length=150, blank=True, null=True)

    montagem_campo = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    montagem_campo_outros = models.CharField(max_length=150, blank=True, null=True)

    equipamento_icamento = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    equipamento_icamento_outros = models.CharField(max_length=150, blank=True, null=True)

    pneumatica = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    pneumatica_outros = models.CharField(max_length=150, blank=True, null=True)

    despoeiramento = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    despoeiramento_outros = models.CharField(max_length=150, blank=True, null=True)

    instrumentos = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM')
    instrumentos_outros = models.CharField(max_length=150, blank=True, null=True)

    destelhamento = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM',
                                     verbose_name="Destelhamento e Telhamento")
    destelhamento_outros = models.CharField(max_length=150, blank=True, null=True)

    jateamento_pintura = models.CharField(max_length=10, choices=OPCOES_SNO, default='SIM',
                                          verbose_name="Jateamento e Pintura em Campo")
    jateamento_pintura_outros = models.CharField(max_length=150, blank=True, null=True)

    informacoes_adicionais = models.TextField(blank=True, null=True, verbose_name="Informações Adicionais do Escopo")

    risco_capacidade_financeira = models.BooleanField(default=False, verbose_name="Capacidade Financeira")
    risco_fabril = models.BooleanField(default=False, verbose_name="Fabril e Capacidade de Produção")
    risco_qualidade = models.BooleanField(default=False, verbose_name="Qualidade")
    risco_requisitos_legais = models.BooleanField(default=False, verbose_name="Requisitos Legais e Estatutários")
    risco_outros = models.CharField(max_length=200, blank=False, null=True, verbose_name="Outros Riscos, Qual?")

    mkt_indicacao = models.BooleanField(default=False, verbose_name="Indicação")
    mkt_linkedin = models.BooleanField(default=False, verbose_name="LinkedIn")
    mkt_site = models.BooleanField(default=False, verbose_name="Site")
    mkt_instagram = models.BooleanField(default=False, verbose_name="Instagram")
    mkt_outros = models.CharField(max_length=150, blank=True, null=True, verbose_name="Outros (Como conheceu)")

    versao_formulario = models.CharField(max_length=20, default='Versão 1', verbose_name='Versão do Formulário STO')

    def __str__(self):
        return f"STO #{self.id} - {self.cliente} ({self.consultor.username})"


class STOImagem(models.Model):
    sto = models.ForeignKey(STO, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField(upload_to='sto_imagens/%Y/%m/')
    descricao = models.CharField(max_length=100, blank=True, null=True, verbose_name="Descrição da Foto (Opcional)")

    def __str__(self):
        return f"Imagem da STO #{self.sto.id}"



class STORevisao(models.Model):
    sto = models.ForeignKey(STO, on_delete=models.CASCADE, related_name='historico_revisoes')
    usuario_modificador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    solicitante = models.CharField(max_length=100, verbose_name='Solicitante da Alteração')
    motivo_alteracao = models.TextField(verbose_name='Descrição da Alteração', default='')
    data_alteracao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Revisão STO #{self.sto.id} por {self.usuario_modificador.username}"

class VersaoFormularioSTO(models.Model):
    versao = models.CharField(max_length=50, verbose_name='Número da Versão (Ex: Versão 3)')
    data_inicio = models.DateField(verbose_name='Data de Início da Vigência')
    data_fim = models.DateField(null=True, blank=True, verbose_name='Data Final da Vigência')

    class Meta:
        ordering = ['-data_inicio']

    def __str__(self):
        return self.versao
