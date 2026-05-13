import uuid
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .tasks import task_notificar_chamado  # Importação da task do Celery


class Chamado(models.Model):
    # --- MANTENDO SUAS LISTAS ORIGINAIS PARA NÃO QUEBRAR O BANCO ---
    PRIORIDADE = [
        ('BAIXA', 'Baixa - Impacto mínimo, sem interrupção'),
        ('MEDIA', 'Média - Impacto localizado, mas não impede o trabalho'),
        ('ALTA', 'Alta - Setor ou processo parcialmente interrompido'),
        ('CRITICA', 'Crítica - Operação da empresa interrompida (atendimento imediato)'),
    ]

    STATUS = [
        ('NOVO', 'Novo (aguardando triagem)'),
        ('ATRIBUIDO', 'Atribuído para análise'),
        ('EM_ANALISE', 'Em análise técnica'),
        ('EM_ATENDIMENTO', 'Em atendimento / execução'),
        ('AGUARDANDO_USUARIO', 'Aguardando resposta'),
        ('AGUARDANDO_APROVACAO', 'Aguardando aprovação (gestor/área responsável)'),
        ('AGUARDANDO_TERCEIRO', 'Aguardando fornecedor / peça / suporte externo'),
        ('RESOLVIDO', 'Resolvido (aguardando validação do usuário)'),
        ('CONCLUIDO', 'Concluído (validado pelo usuário)'),
        ('CANCELADO', 'Cancelado (solicitante desistiu ou chamado duplicado)'),
    ]

    CATEGORIAS = [
        ('HARDWARE', 'Hardware (computadores, notebooks, impressoras, periféricos)'),
        ('SOFTWARE_BASICO', 'Software Básico (sistema operacional, drivers, office)'),
        ('SOFTWARE_CORPORATIVO', 'Sistemas Corporativos (ERP, PROTHEUS, CRM, BI)'),
        ('REDE', 'Rede e Conectividade (internet, VPN, switches, roteadores)'),
        ('ACESSO', 'Gestão de Acessos (criação/remoção de usuários, senhas, permissões)'),
        ('SEGURANCA', 'Segurança da Informação (antivírus, firewall, incidentes, backup)'),
        ('INFRAESTRUTURA', 'Servidores, storage, virtualização, backups'),
        ('BANCO_DADOS', 'Banco de Dados (manutenção, performance, consultas)'),
        ('TELEFONIA', 'Telefonia / VoIP (ramais, softphones, centrais)'),
        ('EMAIL', 'Correio Eletrônico e Colaboração (e-mail, calendário, Teams, Slack)'),
        ('DESENVOLVIMENTO', 'Desenvolvimento (criação de apps, sites, sistemas, automações)'),
        ('MOBILIDADE', 'Dispositivos Móveis (celulares, tablets, configuração de e-mail)'),
        ('NUVEM', 'Serviços em Nuvem (AWS, Azure, Google Workspace, Dropbox)'),
        ('IMPRESSAO', 'Impressão e Digitalização (configuração, manutenção, filas)'),
        ('TREINAMENTO', 'Treinamento e Orientação (uso de sistemas, boas práticas)'),
        ('OUTROS', 'Outros (demandas não classificadas nas categorias anteriores)'),
    ]

    SETORES = [
        ('COMERCIAL', 'Comercial'), ('COMPRAS', 'Compras'), ('DIRETORIA', 'Diretoria'),
        ('FINANCEIRO', 'Financeiro'), ('OBRA', 'Obra'), ('ORCAMENTO', 'Orçamento'),
        ('SGQ', 'SGQ'), ('PRODUCAO', 'Produção'), ('PROJETOS', 'Projetos'),
        ('RECURSOS HUMADOS', 'Recursos Humados'), ('T.I', 'T.I'),
    ]

    # --- CAMPOS ORIGINAIS (MANTIDOS) ---
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
        verbose_name='Técnico Responsável'
    )

    titulo = models.CharField(max_length=100)
    descricao = models.TextField(verbose_name='Descrição do Problema')
    categoria = models.CharField(max_length=30, choices=CATEGORIAS, default='')
    prioridade = models.CharField(max_length=20, choices=PRIORIDADE, default='')
    setor = models.CharField(max_length=50, choices=SETORES, default='')

    data_abertura = models.DateField(auto_now_add=True)
    data_fechamento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS, default='NOVO')
    solucao = models.TextField(verbose_name='Solução Utilizada', blank=True)
    validado_pelo_solicitante = models.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Armazena o status inicial para detectar mudanças sem consultar o banco novamente
        self._original_status = self.status

    def clean(self):
        if self.status == 'CONCLUIDO' and not self.validado_pelo_solicitante:
            raise ValidationError({'status': 'O chamado não pode ser encerrado sem validação do solicitante.'})
        if self.status in ['RESOLVIDO', 'CONCLUIDO'] and not self.solucao:
            raise ValidationError({'solucao': 'Descreva a solução técnica utilizada.'})

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        # Gestão automática de data de fechamento
        if self.status == 'CONCLUIDO' and not self.data_fechamento:
            self.data_fechamento = timezone.now().date()
        elif self.status != 'CONCLUIDO':
            self.data_fechamento = None

        super().save(*args, **kwargs)

        # --- Lógica de Notificação via Celery (Performance & Estabilidade) ---
        if is_new:
            transaction.on_commit(
                lambda: task_notificar_chamado.apply_async(args=[self.id, 'ABERTURA'], countdown=5)
            )
        elif self.status != self._original_status:
            # Notifica apenas se o status realmente mudou
            status_para_task = "CONCLUSAO" if self.status == "CONCLUIDO" else self.status
            transaction.on_commit(
                lambda: task_notificar_chamado.delay(self.id, status_para_task)
            )

    def __str__(self):
        return f"#{self.id} - {self.titulo}"

    def calcular_sla(self):
        if self.prioridade == 'BAIXA': return '1 Dia'
        elif self.prioridade == 'MEDIA': return '8 Horas'
        elif self.prioridade == 'ALTA': return '2 Hora'
        elif self.prioridade == 'CRITICA': return 'Imediato'
        return 'Indefinido'

    def notificar_usuario(self, tipo):
        webhook_user_url = "https://default367afcf4ee4944dfb034fc7437ee90.47.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/16a5c86eb81f49389610d053e5fa42c6/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=p1ycoRGzyZY5w_RGL-sGsuYAiLatbUw1Nb2KnCae0jo"

        texto_msg = ""
        titulo_card = ""

        if tipo == 'ABERTURA':
            sla = self.calcular_sla()
            titulo_card = "Chamado Aberto"
            texto_msg = f"Prioridade: {self.get_prioridade_display()} | Prazo: {sla}"

        elif tipo == 'ATRIBUIDO':
            tecnico_nome = self.tecnico.get_full_name() if self.tecnico else "um técnico"
            titulo_card = "Chamado Atribuído"
            texto_msg = f"Seu chamado foi encaminhado para análise por {tecnico_nome}."

        elif tipo == 'EM_ANALISE':
            titulo_card = "Em Análise Técnica"
            texto_msg = "A equipe de TI está analisando o seu problema neste momento."

        elif tipo == 'EM_ATENDIMENTO':
            titulo_card = "Em Atendimento"
            texto_msg = "O técnico iniciou a execução/atendimento do seu chamado."

        elif tipo == 'AGUARDANDO_TERCEIRO':
            titulo_card = "Aguardando Fornecedor/Peça"
            texto_msg = "O atendimento está pausado aguardando uma peça ou suporte externo."

        elif tipo == 'AGUARDANDO_USUARIO':
            titulo_card = "Aguardando Sua Resposta"
            texto_msg = "O técnico precisa de mais informações para seguir. Verifique seu chamado."

        elif tipo == 'AGUARDANDO_APROVACAO':
            titulo_card = "Aguardando Aprovação"
            texto_msg = "O chamado depende da aprovação do gestor ou área responsável."

        elif tipo == 'RESOLVIDO':
            titulo_card = "Chamado Resolvido (Aguardando Você)"
            texto_msg = f"A TI aplicou a seguinte solução:\n{self.solucao}\n\nPor favor, valide no sistema se o problema foi resolvido."

        elif tipo == 'CONCLUSAO':
            titulo_card = "Chamado Concluído"
            texto_msg = f"Atendimento validado e encerrado.\nSolução: {self.solucao}"

        elif tipo == 'CANCELADO':
            titulo_card = "Chamado Cancelado"
            texto_msg = "A solicitação foi cancelada."

        else:
            titulo_card = "Atualização no Chamado"
            texto_msg = f"O status do seu chamado mudou para: {self.get_status_display()}"

        payload = {
            "Id": self.id,
            "solicitante": self.solicitante.get_full_name() or self.solicitante.username,
            "email": self.solicitante.email,
            "mensagem": texto_msg,
            "titulo": titulo_card
        }

        try:
            print(f"Tentando notificar usuário: {self.solicitante.email} com status {tipo}")
            response = requests.post(webhook_user_url, json=payload)
            print(f"Status Power Automate (User): {response.status_code}")
        except Exception as e:
            print(f"Erro CRÍTICO ao notificar usuario: {e}")

    def enviar_teams_ti(self):
        webhook_url = 'https://default367afcf4ee4944dfb034fc7437ee90.47.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/f862d4b8a3c24bdf9b713b3b555c16b9/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=WsQGdgHELAf2gi8NtGI8mVAt1nK1m9qAvkOZliK4Nz0'

        nome_solicitante = self.solicitante.get_full_name() or self.solicitante.username
        usuario_teams = self.solicitante.teams_username or 'Não cadastrado'

        card_data = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": f"Novo Chamado: {self.titulo}",
            "sections": [{
                "activityTitle": "🚨 Novo Chamado Aberto",
                "activitySubtitle": f"Solicitante: {nome_solicitante}",
                "activityText": f"User Teams: {usuario_teams}",
                "facts": [
                    {"name": "ID:", "value": str(self.id)},
                    {"name": "Setor:", "value": self.get_setor_display()},
                    {"name": "Categoria:", "value": self.get_categoria_display()},
                    {"name": "Prioridade:", "value": self.get_prioridade_display()},
                    {"name": "Título:", "value": self.titulo}
                ],
                "markdown": True
            }]
        }

        try:
            response = requests.post(webhook_url, data=json.dumps(card_data),
                                     headers={'Content-Type': 'application/json'})
            if response.status_code not in [200, 202]:
                print(f'ERRO NO TEAMS (TI): {response.status_code} - {response.text}')
            else:
                print(f'SUCESSO TEAMS (TI): Mensagem enviada para o canal.')
        except Exception as e:
            print(f'Erro de conexão Teams: {e}')

class ChamadoImagem(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField(upload_to='chamados/%Y/%m/')
