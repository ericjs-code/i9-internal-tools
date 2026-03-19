from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from .models import RNC
from django.db import transaction

class RNCService:
    @staticmethod
    def atualizar_rnc(rnc_id, campo, valor):
        with transaction.atomic():
        # Busca a instancia e guarda o estado anterior
            rnc = RNC.objects.get(id=rnc_id)
            valor_antigo = getattr(rnc, campo)

            # tratamento especial para datas, se o campo for data, convertemos para string do JS
            if 'data' in campo and isinstance(valor, str) and valor != '':
                try:
                    valor = datetime.strptime(valor, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # tratamento especial para status
            mapa_status = {
                'Não iniciada': 'NI', 'Em andamento': 'EA', 'Concluido': 'CO', 'Fora dos trilhos': 'FT', 'Registro preliminar': 'PR', 'Cancelado': 'CA'
            }
            if campo =='status' and valor in mapa_status:
                valor = mapa_status[valor]

            setattr(rnc, campo, valor)
            rnc.versao += 1
            rnc.save(update_fields=[campo, 'versao', 'atualizado_em'])

            # gatilho de email apenas se o valor foi alterado
            if campo == 'data_encerramento' and valor != valor_antigo:
                transaction.on_commit(lambda: RNCService._notificar_data_encerramento(rnc.id))

        return rnc

    @staticmethod
    def _notificar_data_encerramento(rnc):
        rnc = RNC.objects.get(id=rnc.id)
        emails = [resp.email for resp in rnc.responsaveis.all() if resp.email]
        if emails:
            try:
                send_mail(
                    subject=f'[SGQ] Alteração de Prazo - RNC #{rnc.id}',
                    message=f'A RNC {rnc.id} teve sua data de encerramento alterada para {rnc.data_encerramento}.',
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=emails,
                    fail_silently=False
                )
            except Exception as e:
                print(f'Erro ao enviar email da RNC {rnc,id}: {e}')