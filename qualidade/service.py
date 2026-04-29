from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from .models import RNC
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()

class RNCService:
    @staticmethod
    def atualizar_rnc(rnc_id, campo, valor):
        with transaction.atomic():
            # Busca a instancia e guarda o estado anterior
            rnc = RNC.objects.get(id=rnc_id)
            valor_antigo = getattr(rnc, campo)

            # tratamento especial para datas, se o campo for data, converte para string do JS
            if 'data' in campo and isinstance(valor, str) and valor != '':
                try:
                    valor = datetime.strptime(valor, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # tratamento especial para status
            mapa_status = {
                'Não iniciada': 'NI', 'Em andamento': 'EA', 'Concluído': 'CO', 'Fora dos trilhos': 'FT', 'Registro preliminar': 'PR', 'Cancelado': 'CA'
            }
            if campo =='status' and valor in mapa_status:
                valor = mapa_status[valor]

            mapa_detector = {
                'Cliente': 'CL', 'Interno': 'IN', 'Auditor Interno': 'AI', 'Auditor Externo': 'AE', 'Fornecedor': 'FO'
            }
            if campo =='detector' and valor in mapa_detector:
                valor = mapa_detector[valor]

            mapa_categoria = {'Comercial': 'CO', 'Engenharia': 'EN', 'PCP': 'PC', 'Fabricação': 'FA', 'Montagem': 'MO', 'Suprimentos': 'SU', 'Fornecedor': 'FO', 'Expedição': 'EX', 'Qualidade': 'QU', 'Recursos Humanos': 'RH', 'Financeiro': 'FI', 'SGQ': 'SG'}
            if campo =='categoria' and valor in mapa_categoria:
                valor = mapa_categoria[valor]

            mapa_criticidade = {'Alto': 'A', 'Médio': 'M', 'Baixo': 'B'}
            if campo == 'criticidade' and valor in mapa_criticidade:
                valor = mapa_criticidade[valor]

            mapa_origem = {'Comercial': 'CO', 'Projeto_Engenharia': 'PE', 'Fabricação': 'FA', 'Montagem_comissionamento': 'MC', 'Suprimentos': 'SU', 'RH': 'RH', 'Fornecedor': 'FO', 'Processo_interno_SGQ': 'SG'}
            if campo =='origem' and valor in mapa_origem:
                valor = mapa_origem[valor]

            setattr(rnc, campo, valor)
            rnc.versao += 1
            rnc.save(update_fields=[campo, 'versao', 'atualizado_em'])

            # gatilho de email apenas se o valor foi alterado
            if campo == 'data_encerramento' and valor != valor_antigo:
                transaction.on_commit(lambda: RNCService._notificar_data_encerramento(rnc.id))

        return rnc

    @staticmethod
    def _notificar_data_encerramento(rnc_id):
        rnc = RNC.objects.get(id=rnc_id)
        emails = [resp.email for resp in rnc.responsaveis.all() if resp.email]

        if emails:
            nome_equipamento = rnc.equipamento.nome if rnc.equipamento else "Não informado"
            codigo_projeto = rnc.projeto_cod if rnc.projeto_cod else "Não informado"

            email_altera_data = (
                f"Atenção, a data de encerramento da RNC foi atualizada.\n\n"
                f"Clique aqui para acessar: https://inovetmg.pythonanywhere.com/login/\n\n"
                f"DETALHES DA RNC:\n"
                f"- ID: {rnc.id}\n"
                f"- Equipamento: {nome_equipamento}\n"
                f"- Projeto: {codigo_projeto}\n"
                f"- Descrição da Não Conformidade: {rnc.descricao}\n\n"
                f"Nova Data de Encerramento: {rnc.data_encerramento.strftime('%d/%m/%Y') if rnc.data_encerramento else 'Não informado'}\n"
            )

            try:
                send_mail(
                    subject=f'[SGQ] Alteração de Prazo - RNC #{rnc.id}',
                    message=email_altera_data,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=emails,
                    fail_silently=False
                )
            except Exception as e:
                print(f'Erro ao enviar email da RNC {rnc.id}: {e}')

    @staticmethod
    def _notificar_novo_responsavel(rnc_id, usuario_id):
        # Busca RNC, user e email no banco de dados
        rnc = RNC.objects.get(id=rnc_id)
        usuario = User.objects.get(id=usuario_id)
        email = usuario.email

        if email:
            # Monta email
            nome_equipamento = rnc.equipamento.nome if rnc.equipamento else "Não informado"
            local = rnc.local if rnc.local else "Não informado"
            registrador = rnc.registrador
            criticidade = rnc.criticidade

            email_novo_resp = (
                f"Atenção, você foi citado em uma RNC.\n\n"
                f"Clique aqui para acessar: https://inovetmg.pythonanywhere.com/login/\n\n"
                f"DETALHES DA RNC:\n"
                f"- ID: {rnc.id}\n"
                f"- Equipamento: {nome_equipamento}\n"
                f"- Local: {local}\n"
                f"- Registrador: {registrador}\n"
                f"- Descrição da Não Conformidade: {rnc.descricao}\n\n"
            )

            # Dispara email com send_mail
            try:
                send_mail(
                    subject=f'[SGQ] Você foi citado em uma nova RNC - RNC #{rnc.id}',
                    message=email_novo_resp,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[email],
                    fail_silently=False
                )
            except Exception as e:
                print(f'Erro ao enviar email da RNC {rnc.id}: {e}')

    @staticmethod
    def notificar_nova_rnc(rnc_id, lista_usuario_id):
        for usuario_id in lista_usuario_id:
            RNCService._notificar_novo_responsavel(rnc_id, usuario_id)

    @staticmethod
    def _notificar_data_previsao(rnc_id):
        rnc = RNC.objects.get(id=rnc_id)
        emails = [resp.email for resp in rnc.responsaveis.all() if resp.email]

        if emails:
            nome_equipamento = rnc.equipamento.nome if rnc.equipamento else "Não informado"
            codigo_projeto = rnc.projeto_cod if rnc.projeto_cod else "Não informado"

            email_altera_data = (
                f"Atenção, a data de previsão de encerramento da RNC foi atualizada.\n\n"
                f"Clique aqui para acessar: https://inovetmg.pythonanywhere.com/login/ \n\n"
                f"DETALHES DA RNC:\n"
                f"- ID: {rnc.id}\n"
                f"- Equipamento: {nome_equipamento}\n"
                f"- Projeto: {codigo_projeto}\n"
                f"- Descrição da Não Conformidade: {rnc.descricao}\n\n"
                f"Nova Data de previsão de encerramento: {rnc.data_prevista_conclusao.strftime('%d/%m/%Y') if rnc.data_prevista_conclusao else 'Não informado'}\n"
            )

            try:
                send_mail(
                    subject=f'[SGQ] Alteração de Prazo - RNC #{rnc.id}',
                    message=email_altera_data,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=emails,
                    fail_silently=False
                )
            except Exception as e:
                print(f'Erro ao enviar email da RNC {rnc.id}: {e}')

    @staticmethod
    def notificar_alerta_vencimento(rnc_id, dias_restantes):
        rnc = RNC.objects.get(id=rnc_id)
        emails = [resp.email for resp in rnc.responsaveis.all() if resp.email]

        if emails:
            nome_equipamento = rnc.equipamento.nome if rnc.equipamento else "Não informado"
            codigo_projeto = rnc.projeto_cod if rnc.projeto_cod else "Não informado"

            termo_dia = "AMANHÃ" if dias_restantes == 1 else f"em {dias_restantes} dias"

            email_alerta = (
                f"Atenção! A data de previsão de encerramento da RNC vence {termo_dia}.\n\n"
                f"Clique aqui para acessar: https://inovetmg.pythonanywhere.com/login/ \n\n"
                f"DETALHES DA RNC:\n"
                f"- ID: {rnc.id}\n"
                f"- Equipamento: {nome_equipamento}\n"
                f"- Projeto: {codigo_projeto}\n"
                f"- Descrição: {rnc.descricao}\n\n"
                f"Data Limite: {rnc.data_prevista_conclusao.strftime('%d/%m/%Y')}\n"
            )

            try:
                send_mail(
                    subject=f'[SGQ] ALERTA DE VENCIMENTO ({termo_dia}) - RNC #{rnc.id}',
                    message=email_alerta,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=emails,
                    fail_silently=False
                )
            except Exception as e:
                print(f'Erro ao enviar email da RNC {rnc.id}: {e}')


