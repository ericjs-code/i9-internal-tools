from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, verbose_name='Email Corporativo')
    must_change_password = models.BooleanField(default=False, verbose_name='Deve trocar senha no proximo login')
    teams_username = models.CharField(max_length=100, blank=True, null=True, verbose_name='Usuário Teams')

    # Os campos is_comercial, is_ti, is_financeiro, is_rh, is_engenharia, 
    # is_diretoria, is_compras, is_pcp, is_qualidade, is_rdo foram removidos na Fase 3 do RBAC.
    # O controle de acesso agora é feito exclusivamente via django.contrib.auth.models.Group

    def __str__(self):
        return self.get_full_name() or self.username
