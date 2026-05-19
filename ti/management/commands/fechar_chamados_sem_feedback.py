from django.core.management.base import BaseCommand

from ti.services import fechar_chamados_resolvidos_sem_feedback


class Command(BaseCommand):
    help = 'Fecha chamados resolvidos ha 3 dias sem retorno de validacao do solicitante.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=3,
            help='Quantidade de dias sem feedback para fechamento automatico.',
        )

    def handle(self, *args, **options):
        dias = options['dias']
        chamados_fechados = fechar_chamados_resolvidos_sem_feedback(dias_sem_feedback=dias)

        self.stdout.write(
            self.style.SUCCESS(
                f'{len(chamados_fechados)} chamados fechados automaticamente: {chamados_fechados}'
            )
        )
