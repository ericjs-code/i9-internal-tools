from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Chamado(models.Model):
    PRIORIDADE = [
        ('BAIXA', 'Baixa - Impacto minimo, sem interrupcao'),
        ('MEDIA', 'Media - Impacto localizado, mas nao impede o trabalho'),
        ('ALTA', 'Alta - Setor ou processo parcialmente interrompido'),
        ('CRITICA', 'Critica - Operacao da empresa interrompida (atendimento imediato)'),
    ]

    STATUS = [
        ('NOVO', 'Novo (aguardando triagem)'),
        ('ATRIBUIDO', 'Atribuido para analise'),
        ('EM_ANALISE', 'Em analise tecnica'),
        ('EM_ATENDIMENTO', 'Em atendimento / execucao'),
        ('AGUARDANDO_USUARIO', 'Aguardando resposta'),
        ('AGUARDANDO_APROVACAO', 'Aguardando aprovacao (gestor/area responsavel)'),
        ('AGUARDANDO_TERCEIRO', 'Aguardando fornecedor / peca / suporte externo'),
        ('RESOLVIDO', 'Resolvido (aguardando validacao do usuario)'),
        ('CONCLUIDO', 'Concluido (validado pelo usuario)'),
        ('CANCELADO', 'Cancelado (solicitante desistiu ou chamado duplicado)'),
    ]

    CATEGORIAS = [
        ('HARDWARE', 'Hardware (computadores, notebooks, impressoras, perifericos)'),
        ('SOFTWARE_BASICO', 'Software Basico (sistema operacional, drivers, office)'),
        ('SOFTWARE_CORPORATIVO', 'Sistemas Corporativos (ERP, PROTHEUS, CRM, BI)'),
        ('REDE', 'Rede e Conectividade (internet, VPN, switches, roteadores)'),
        ('ACESSO', 'Gestao de Acessos (criacao/remocao de usuarios, senhas, permissoes)'),
        ('SEGURANCA', 'Seguranca da Informacao (antivirus, firewall, incidentes, backup)'),
        ('INFRAESTRUTURA', 'Servidores, storage, virtualizacao, backups'),
        ('BANCO_DADOS', 'Banco de Dados (manutencao, performance, consultas)'),
        ('TELEFONIA', 'Telefonia / VoIP (ramais, softphones, centrais)'),
        ('EMAIL', 'Correio Eletronico e Colaboracao (e-mail, calendario, Teams, Slack)'),
        ('DESENVOLVIMENTO', 'Desenvolvimento (criacao de apps, sites, sistemas, automacoes)'),
        ('MOBILIDADE', 'Dispositivos Moveis (celulares, tablets, configuracao de e-mail)'),
        ('NUVEM', 'Servicos em Nuvem (AWS, Azure, Google Workspace, Dropbox)'),
        ('IMPRESSAO', 'Impressao e Digitalizacao (configuracao, manutencao, filas)'),
        ('TREINAMENTO', 'Treinamento e Orientacao (uso de sistemas, boas praticas)'),
        ('OUTROS', 'Outros (demandas nao classificadas nas categorias anteriores)'),
    ]

    SETORES = [
        ('COMERCIAL', 'Comercial'),
        ('COMPRAS', 'Compras'),
        ('DIRETORIA', 'Diretoria'),
        ('FINANCEIRO', 'Financeiro'),
        ('OBRA', 'Obra'),
        ('ORCAMENTO', 'Orcamento'),
        ('SGQ', 'SGQ'),
        ('PRODUCAO', 'Producao'),
        ('PROJETOS', 'Projetos'),
        ('RECURSOS HUMANOS', 'Recursos Humanos'),
        ('T.I', 'T.I'),
    ]

    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='chamados_abertos',
        verbose_name='Solicitante',
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='chamados_atendidos',
        null=True,
        blank=True,
        verbose_name='Tecnico Responsavel',
    )

    titulo = models.CharField(max_length=100)
    descricao = models.TextField(verbose_name='Descricao do Problema')
    categoria = models.CharField(max_length=30, choices=CATEGORIAS, default='')
    prioridade = models.CharField(max_length=20, choices=PRIORIDADE, default='')
    setor = models.CharField(max_length=50, choices=SETORES, default='')

    data_abertura = models.DateTimeField(auto_now_add=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS, default='NOVO')
    solucao = models.TextField(verbose_name='Solucao Utilizada', blank=True)
    validado_pelo_solicitante = models.BooleanField(default=False)
    encerrado_automaticamente = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(
                fields=['status', 'validado_pelo_solicitante', 'encerrado_automaticamente', 'data_resolucao'],
                name='ti_chamado_auto_close_idx',
            ),
        ]

    def clean(self):
        if (
            self.status == 'CONCLUIDO'
            and not self.validado_pelo_solicitante
            and not self.encerrado_automaticamente
        ):
            raise ValidationError({'status': 'O chamado nao pode ser encerrado sem validacao do solicitante.'})
        if self.status in ['RESOLVIDO', 'CONCLUIDO'] and not self.solucao:
            raise ValidationError({'solucao': 'Descreva a solucao tecnica utilizada.'})

    def save(self, *args, **kwargs):
        if self.status == 'RESOLVIDO' and not self.data_resolucao:
            self.data_resolucao = timezone.now()
        elif self.status not in ['RESOLVIDO', 'CONCLUIDO']:
            self.data_resolucao = None
            self.encerrado_automaticamente = False

        if self.status == 'CONCLUIDO' and not self.data_fechamento:
            self.data_fechamento = timezone.now()
        elif self.status != 'CONCLUIDO':
            self.data_fechamento = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.id} - {self.titulo}"

    def calcular_sla(self):
        if self.prioridade == 'BAIXA':
            return '1 Dia'
        if self.prioridade == 'MEDIA':
            return '8 Horas'
        if self.prioridade == 'ALTA':
            return '2 Horas'
        if self.prioridade == 'CRITICA':
            return 'Imediato'
        return 'Indefinido'


class ChamadoImagem(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField(upload_to='chamados/%Y/%m/')
