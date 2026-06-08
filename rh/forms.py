import re
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from phonenumber_field.formfields import PhoneNumberField
from .constants import ORGAOS_EXPEDIDORES_RG, get_municipios_brasileiros_choices
from .models import (Candidatura, Vaga, SolicitacaoVaga, PesquisaDemissional,
                     FormularioAdmissional, DependenteAdmissional)


class CandidaturaForm(forms.ModelForm):
    class Meta:
        model = Candidatura
        fields = ['nome_completo', 'email', 'telefone', 'linkedin', 'curriculo']
        widgets = {
            'nome_completo': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'linkedin': forms.URLInput(attrs={'class': 'form-control'}),
            'curriculo': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx'}),
        }

class VagaForm(forms.ModelForm):
    class Meta:
        model = Vaga
        fields = ['titulo', 'setor', 'descricao', 'requisitos', 'ativa']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Analista de TI Sênior'}),
            'setor': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Descreva o dia a dia da função, responsabilidades e desafios...'}),
            'requisitos': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Ex: Superior completo, experiência com Python, Django, etc...'}),
            'ativa': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
        }

class SolicitacaoVagaForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoVaga
        exclude = ['solicitante', 'data_solicitacao', 'status', 'observacoes_rh']

        widgets = {
            'data_prevista_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cargo_solicitante': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ex: Gerente de Obras'}),
            'nome_vaga': forms.TextInput(attrs={'class': 'form-control'}),
            'quantidade_vagas': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'motivo': forms.Select(attrs={'class': 'form-select'}),
            'nome_substituido': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Preencha apenas em caso de substituição'}),
            'sexo': forms.Select(attrs={'class': 'form-select'}),
            'escolaridade': forms.Select(attrs={'class': 'form-select'}),
            'curso_area': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ex: Engenharia Civil, Administração...'}),
            'descricao_atividades': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'conhecimentos_desejaveis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'atitudes_desejaveis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'observacoes_gerais': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_data_prevista_inicio(self):
        data = self.cleaned_data.get('data_prevista_inicio')
        if data:
            if data.weekday() != 0:
                raise ValidationError(
                    "A política da empresa exige que as admissões ocorram sempre em uma Segunda-feira. Por favor, ajuste a data.")
        return data

    def clean(self):
        cleaned_data = super().clean()
        motivo = cleaned_data.get('motivo')
        nome_substituido = cleaned_data.get('nome_substituido')

        if motivo and 'SUBST' in motivo:
            if not nome_substituido:
                self.add_error('nome_substituido',
                               'Como o motivo é substituição, é obrigatório informar o nome de quem está saindo.')

        return cleaned_data

class PesquisaDemissionalGeracaoForm(forms.ModelForm):
    """
    Formulario exclusivo para o RH gerar link da pesquisa
    """
    class Meta:
        model = PesquisaDemissional
        fields = ['ex_funcionario_nome', 'setor', 'tipo_demissao', 'periodo_saida', 'tempo_casa']
        widgets = {
            'periodo_saida': forms.TextInput(attrs={'placeholder': 'Ex: Março/2026'}),
            'tempo_casa': forms.TextInput(attrs={'placeholder': 'Ex: 2 anos e 3 meses'})
        }

class PesquisaDemissionalRespostaForm(forms.ModelForm):
    """
    Formulario publico para o ex-colaborador responder
    """
    class Meta:
        model = PesquisaDemissional
        fields = [
            'motivo_saida', 'diferente', 'nota_lideranca',
            'nota_oportunidade', 'nota_reconhecimento',
            'nota_clima', 'nota_recomendacao'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        escala_1_a_5 = ['nota_lideranca', 'nota_oportunidade', 'nota_reconhecimento', 'nota_clima']
        for field in escala_1_a_5:
            self.fields[field].widget = forms.NumberInput(attrs={'min': 1, 'max': 5, 'required': True})

        self.fields['nota_recomendacao'].widget = forms.NumberInput(attrs={'min': 0, 'max': 10, 'required': True})

        self.fields['diferente'].widget = forms.Textarea(attrs={'rows': 4})


class FormularioAdmissionalGeracaoForm(forms.ModelForm):
    """
    Formulario interno para o RH gerar link admissional.
    """
    class Meta:
        model = FormularioAdmissional
        fields = ['candidato_nome_interno']
        widgets = {
            'candidato_nome_interno': forms.TextInput(attrs={'class': 'form-control'})
        }


class FormularioAdmissionalRespostaForm(forms.ModelForm):
    """
    Formulario publico para preenchimento admissional.
    """
    telefone_principal = PhoneNumberField(region='BR', error_messages={'invalid': 'Informe um telefone brasileiro valido.'})
    contato_recado = PhoneNumberField(region='BR', error_messages={'invalid': 'Informe um telefone brasileiro valido para recado.'})

    campos_obrigatorios = [
        'nome_completo', 'cpf', 'funcao_pretendida',
        'pis', 'numero_ctps', 'uf_ctps',
        'cep', 'endereco', 'bairro', 'cidade_estado',
        'telefone_principal', 'contato_recado', 'email',
        'data_nascimento', 'estado_nascimento', 'naturalidade', 'cor_raca',
        'grau_instrucao', 'nome_mae', 'nome_pai',
        'numero_rg', 'orgao_expedidor', 'uf_rg', 'data_emissao_rg',
        'estado_civil', 'possui_dependentes_ir',
        'botina', 'camisa', 'calca',
        'utiliza_vale_transporte', 'lgpd_consentimento',
    ]

    class Meta:
        model = FormularioAdmissional
        fields = [
            'nome_completo', 'cpf', 'funcao_pretendida',
            'pis', 'numero_ctps', 'serie_ctps', 'uf_ctps',
            'cep', 'endereco', 'bairro', 'cidade_estado',
            'telefone_principal', 'contato_recado', 'email',
            'data_nascimento', 'estado_nascimento', 'naturalidade', 'cor_raca',
            'grau_instrucao', 'nome_mae', 'nome_pai',
            'numero_rg', 'orgao_expedidor', 'uf_rg', 'data_emissao_rg',
            'titulo_eleitor', 'zona_eleitoral', 'secao_eleitoral', 'uf_titulo_eleitor',
            'reservista', 'numero_cnh', 'validade_cnh', 'estado_cnh',
            'estado_civil', 'possui_dependentes_ir',
            'botina', 'camisa', 'calca',
            'utiliza_vale_transporte', 'trajeto_vale_transporte', 'lgpd_consentimento',
        ]
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'data_emissao_rg': forms.DateInput(attrs={'type': 'date'}),
            'validade_cnh': forms.DateInput(attrs={'type': 'date'}),
            'trajeto_vale_transporte': forms.Textarea(attrs={'rows': 3}),
            'lgpd_consentimento': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for nome, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

        for nome in self.campos_obrigatorios:
            self.fields[nome].required = True

        self.fields['cidade_estado'].help_text = 'Ex.: Araucária-PR'
        self.fields['funcao_pretendida'].help_text = 'Ex.: Ajudante, Soldador, Assistente Administrativo'
        self.fields['endereco'].help_text = 'Rua e número'
        self.fields['bairro'].label = 'Bairro'
        self.fields['naturalidade'].help_text = 'Cidade onde nasceu'
        self.fields['trajeto_vale_transporte'].required = False
        self.fields['trajeto_vale_transporte'].help_text = 'Informe as linhas, terminais ou o caminho utilizado entre sua residência e o trabalho.'
        self.fields['serie_ctps'].required = False
        self.fields['titulo_eleitor'].required = False
        self.fields['zona_eleitoral'].required = False
        self.fields['secao_eleitoral'].required = False
        self.fields['uf_titulo_eleitor'].required = False
        self.fields['reservista'].required = False
        self.fields['numero_cnh'].required = False
        self.fields['validade_cnh'].required = False
        self.fields['estado_cnh'].required = False
        self.fields['orgao_expedidor'].choices = [('', 'Selecione')] + list(ORGAOS_EXPEDIDORES_RG)
        self.fields['naturalidade'].widget = forms.Select(
            choices=[('', 'Selecione')] + list(get_municipios_brasileiros_choices()),
            attrs={'class': 'form-select'}
        )

        self.fields['cor_raca'].choices = [
            ('', '---------'),
            ('BRANCA', 'Branca'),
            ('PRETA', 'Preta'),
            ('PARDA', 'Parda'),
            ('AMARELA', 'Amarela'),
            ('INDIGENA', 'Indígena'),
            ('NAO_INFORMAR', 'Prefiro não informar'),
        ]
        self.fields['grau_instrucao'].choices = [
            ('', '---------'),
            ('FUND_INCOMPLETO', 'Ensino Fundamental Incompleto'),
            ('FUND_COMPLETO', 'Ensino Fundamental Completo'),
            ('MEDIO_INCOMPLETO', 'Ensino Médio Incompleto'),
            ('MEDIO_COMPLETO', 'Ensino Médio Completo'),
            ('SUPERIOR_INCOMPLETO', 'Ensino Superior Incompleto'),
            ('SUPERIOR_COMPLETO', 'Ensino Superior Completo'),
            ('POS_GRADUACAO', 'Pós-graduação'),
            ('MESTRADO', 'Mestrado'),
            ('DOUTORADO', 'Doutorado'),
        ]
        self.fields['estado_civil'].choices = [
            ('', '---------'),
            ('SOLTEIRO', 'Solteiro(a)'),
            ('CASADO', 'Casado(a)'),
            ('UNIAO_ESTAVEL', 'União Estável'),
            ('DIVORCIADO', 'Divorciado(a)'),
            ('SEPARADO', 'Separado(a)'),
            ('VIUVO', 'Viúvo(a)'),
        ]
        self.fields['possui_dependentes_ir'].choices = [
            ('', '---------'),
            ('SIM', 'Sim'),
            ('NAO', 'Não'),
        ]
        self.fields['utiliza_vale_transporte'].choices = [
            ('', '---------'),
            ('SIM', 'Sim'),
            ('NAO', 'Não'),
        ]

    def clean_cpf(self):
        cpf = self._numero_sem_formatacao('cpf')
        if len(cpf) != 11:
            raise ValidationError('CPF deve conter exatamente 11 digitos.')
        return cpf

    def clean_cep(self):
        cep = self._numero_sem_formatacao('cep')
        if len(cep) != 8:
            raise ValidationError('CEP deve conter exatamente 8 digitos.')
        return cep

    def clean_pis(self):
        pis = self._numero_sem_formatacao('pis')
        if len(pis) != 11:
            raise ValidationError('PIS deve conter exatamente 11 digitos.')
        return pis

    def clean_numero_ctps(self):
        numero_ctps = self._numero_sem_formatacao('numero_ctps')
        if not numero_ctps or len(numero_ctps) > 11:
            raise ValidationError('Numero da CTPS deve conter apenas numeros e no maximo 11 digitos.')
        return numero_ctps

    def clean_serie_ctps(self):
        serie_ctps = self._numero_sem_formatacao('serie_ctps')
        if serie_ctps and len(serie_ctps) != 4:
            raise ValidationError('Serie da CTPS deve conter exatamente 4 digitos quando preenchida.')
        return serie_ctps or None

    def clean_numero_rg(self):
        numero_rg = self._numero_sem_formatacao('numero_rg')
        if not numero_rg or len(numero_rg) > 9:
            raise ValidationError('Numero do RG deve conter apenas numeros e no maximo 9 digitos.')
        return numero_rg

    def clean_titulo_eleitor(self):
        titulo_eleitor = self._numero_sem_formatacao('titulo_eleitor')
        if titulo_eleitor and len(titulo_eleitor) > 12:
            raise ValidationError('Titulo de eleitor deve conter no maximo 12 digitos.')
        return titulo_eleitor or None

    def clean_numero_cnh(self):
        numero_cnh = self._numero_sem_formatacao('numero_cnh')
        if numero_cnh and len(numero_cnh) != 9:
            raise ValidationError('Numero da CNH deve conter exatamente 9 digitos quando preenchido.')
        return numero_cnh or None

    def clean_lgpd_consentimento(self):
        consentimento = self.cleaned_data.get('lgpd_consentimento')
        if not consentimento:
            raise ValidationError('E necessario aceitar o uso dos dados para fins admissionais e obrigacoes legais.')
        return consentimento

    def _numero_sem_formatacao(self, campo):
        valor = self.cleaned_data.get(campo) or ''
        if re.search(r'[A-Za-zÀ-ÿ]', valor):
            raise ValidationError('Use apenas numeros neste campo.')
        return re.sub(r'\D', '', valor)

    def clean(self):
        cleaned_data = super().clean()
        utiliza_vale_transporte = cleaned_data.get('utiliza_vale_transporte')
        trajeto_vale_transporte = cleaned_data.get('trajeto_vale_transporte')
        telefone_principal = cleaned_data.get('telefone_principal')
        contato_recado = cleaned_data.get('contato_recado')

        if utiliza_vale_transporte == 'SIM' and not trajeto_vale_transporte:
            self.add_error('trajeto_vale_transporte', 'Informe o trajeto caso utilize vale transporte.')

        if utiliza_vale_transporte == 'NAO':
            cleaned_data['trajeto_vale_transporte'] = ''

        if telefone_principal and contato_recado and telefone_principal.as_e164 == contato_recado.as_e164:
            self.add_error('contato_recado', 'O contato para recado não pode ser igual ao telefone principal.')

        return cleaned_data


class DependenteAdmissionalForm(forms.ModelForm):
    class Meta:
        model = DependenteAdmissional
        fields = ['nome_completo', 'data_nascimento', 'rg', 'cpf', 'cidade_estado_nascimento']
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    def clean_cpf(self):
        valor = self.cleaned_data.get('cpf') or ''
        if re.search(r'[A-Za-zÀ-ÿ]', valor):
            raise ValidationError('Use apenas numeros no CPF do dependente.')
        cpf = re.sub(r'\D', '', valor)
        if cpf and len(cpf) != 11:
            raise ValidationError('CPF do dependente deve conter 11 digitos.')
        return cpf

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data

        valores = [
            cleaned_data.get('nome_completo'),
            cleaned_data.get('data_nascimento'),
            cleaned_data.get('rg'),
            cleaned_data.get('cpf'),
            cleaned_data.get('cidade_estado_nascimento'),
        ]
        preenchidos = [valor for valor in valores if valor]

        if preenchidos and len(preenchidos) < len(valores):
            raise ValidationError('Preencha todos os campos do dependente ou deixe a linha em branco.')

        return cleaned_data


DependenteAdmissionalFormSet = inlineformset_factory(
    FormularioAdmissional,
    DependenteAdmissional,
    form=DependenteAdmissionalForm,
    extra=2,
    can_delete=True,
)
