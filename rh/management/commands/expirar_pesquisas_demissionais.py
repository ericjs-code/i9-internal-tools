from django.core.management.base import BaseCommand
from django.utils import timezone

from rh.models import PesquisaDemissional


class Command(BaseCommand):
    help = 'Expira pesquisas demissionais pendentes com prazo vencido.'

    def handle(self, *args, **options):
        quantidade = PesquisaDemissional.objects.filter(
            status=PesquisaDemissional.STATUS.PENDENTE,
            data_expiracao__lt=timezone.now(),
        ).update(status=PesquisaDemissional.STATUS.EXPIRADA)

        self.stdout.write(
            self.style.SUCCESS(f'{quantidade} pesquisa(s) demissional(is) expirada(s).')
        )
