from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, verbose_name='Email Corporativo')
    teams_username = models.CharField(max_length=100, blank=True, null=True, verbose_name='Usuário Teams')
    is_comercial = models.BooleanField(default=False, verbose_name='Acesso Comercial')
    is_ti = models.BooleanField(default=False, verbose_name='Acesso TI')
    is_financeiro = models.BooleanField(default=False, verbose_name='Acesso Financeiro')
    is_rh = models.BooleanField(default=False, verbose_name="Acesso RH")
    is_engenharia = models.BooleanField(default=False, verbose_name="Acesso Engenharia")
    is_diretoria = models.BooleanField(default=False, verbose_name="Acesso Diretoria (Total)")
    is_compras = models.BooleanField(default=False, verbose_name="Acesso Compras")
    is_pcp = models.BooleanField(default=False, verbose_name="Acesso PCP")
    is_qualidade = models.BooleanField(default=False, verbose_name="Acesso Qualidade")


    def __str__(self):
        return self.get_full_name() or self.username

    def pode_acessar_modulo(self, modulo):
        if self.is_diretoria or self.is_ti or self.is_superuser:
            return True

        permissoes = {
            'comercial': self.is_comercial,
            'financeiro': self.is_financeiro,
            'rh': self.is_rh,
            'engenharia': self.is_engenharia,
            'compras': self.is_compras,
            'pcp': self.is_pcp,
            'qualidade': self.is_qualidade,
        }
        return permissoes.get(modulo, False)