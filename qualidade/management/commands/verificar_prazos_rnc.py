from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from qualidade.models import RNC
from qualidade.service import RNCService


class Command(BaseCommand):
    help = 'Verifica RNCs próximas do vencimento e envia e-mails de alerta aos responsáveis.'

    def handle(self, *args, **kwargs):
        hoje = timezone.now().date()
        data_alvo_7_dias = hoje + timedelta(days=7)
        data_alvo_1_dia = hoje + timedelta(days=1)

        self.stdout.write(self.style.WARNING(f'Iniciando varredura. Hoje é {hoje}...'))

        rncs_ativas = RNC.objects.exclude(status__in=['CO', 'CA'])
        rncs_7_dias = rncs_ativas.filter(data_prevista_conclusao=data_alvo_7_dias)
        rncs_1_dia = rncs_ativas.filter(data_prevista_conclusao=data_alvo_1_dia)

        for rnc in rncs_7_dias:
            if rnc.responsaveis.exists():
                self.stdout.write(f"Alerta de 7 dias para RNC #{rnc.id}")
                RNCService.notificar_alerta_vencimento(rnc.id, 7)

        for rnc in rncs_1_dia:
            if rnc.responsaveis.exists():
                self.stdout.write(f"Alerta de 1 dia para RNC #{rnc.id}")
                RNCService.notificar_alerta_vencimento(rnc.id, 1)

        self.stdout.write(self.style.SUCCESS('Varredura concluída com sucesso!'))