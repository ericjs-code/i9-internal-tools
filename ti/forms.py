from django import forms
from .models import Chamado
from django.contrib.auth import get_user_model

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={'class': 'form-control'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class ChamadoForm(forms.ModelForm):
    imagens = MultipleFileField(
        required=False,
        label="Anexar Prints/Fotos (Você pode selecionar várias de uma vez)"
    )

    class Meta:
        model = Chamado
        fields = ['titulo', 'setor', 'categoria', 'prioridade', 'descricao']

class AtendimentoChamadoForm(forms.ModelForm):
    class Meta:
        model = Chamado
        fields = ['status', 'prioridade', 'categoria', 'setor', 'solucao']
        widgets = {
            'solucao': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Descreva detalhadamente a solução técnica aplicada para resolver este chamado...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and not self.instance.validado_pelo_solicitante:
            opcoes_atuais = list(self.fields['status'].choices)
            self.fields['status'].choices = [opcao for opcao in opcoes_atuais if opcao[0] != 'CONCLUIDO']

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')

        if status == 'CONCLUIDO' and self.instance and not self.instance.validado_pelo_solicitante:
            self.add_error('status',
                           'OPERAÇÃO BLOQUEADA (ITIL): Apenas o usuário pode encerrar o chamado. Altere o status para "Resolvido".')

        return cleaned_data

User = get_user_model()
class UsuarioForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False,
        label="Senha",
        help_text="Preencha apenas quando for criar um novo user ou alterar a senha atual."
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'teams_username',
            'is_active', 'is_comercial', 'is_rh', 'is_ti', 'is_financeiro',
            'is_engenharia', 'is_compras', 'is_pcp', 'is_diretoria', 'is_qualidade']

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')

        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user