import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CustomUser


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='usuario.reset',
            email='usuario.reset@example.com',
            password='senha-antiga-123',
            is_active=True,
        )

    def test_envia_email_de_redefinicao_para_usuario_ativo(self):
        response = self.client.post(reverse('password_reset'), {'email': self.user.email})

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Redefinicao de senha', mail.outbox[0].subject)
        self.assertIn('/senha/redefinir/', mail.outbox[0].body)

    def test_nao_enumera_email_inexistente(self):
        response = self.client.post(reverse('password_reset'), {'email': 'naoexiste@example.com'})

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_redefine_senha_com_token_valido_e_invalida_reuso(self):
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        reset_url = re.search(r'/senha/redefinir/[^/]+/[^/]+/', mail.outbox[0].body).group(0)

        response = self.client.get(reset_url)
        self.assertEqual(response.status_code, 302)
        confirm_url = response['Location']

        response = self.client.post(confirm_url, {
            'new_password1': 'nova-senha-forte-456',
            'new_password2': 'nova-senha-forte-456',
        })

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('nova-senha-forte-456'))

        reused_response = self.client.get(reset_url)
        self.assertEqual(reused_response.status_code, 200)
        self.assertContains(reused_response, 'Link invalido ou expirado')
