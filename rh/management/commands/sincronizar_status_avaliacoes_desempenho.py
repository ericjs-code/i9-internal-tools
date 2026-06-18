from django.core.management.base import BaseCommand

from rh.models import AvaliacaoDesempenho


class Command(BaseCommand):
    help = 'Sincroniza status das avaliacoes de desempenho com base nas ciencias registradas.'

    def handle(self, *args, **options):
        total = 0

        for avaliacao in AvaliacaoDesempenho.objects.all():
            status_antigo = avaliacao.status
            bloqueada_antigo = avaliacao.bloqueada
            avaliacao.atualizar_status_ciencia()

            if avaliacao.status != status_antigo or avaliacao.bloqueada != bloqueada_antigo:
                avaliacao.save(update_fields=['status', 'bloqueada', 'atualizado_em'])
                total += 1

        self.stdout.write(
            self.style.SUCCESS(f'{total} avaliacoes tiveram o status sincronizado.')
        )
