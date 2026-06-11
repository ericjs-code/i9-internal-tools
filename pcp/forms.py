from __future__ import annotations

from typing import Any

from django import forms

from pcp.models import (
    PcpAtivo,
    PcpEvidenciaManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    StatusManutencao,
    TipoDowntime,
    TipoManutencao,
)


class BootstrapFormMixin:
    def aplicar_bootstrap(self) -> None:
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class


class PcpAtivoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PcpAtivo
        fields = [
            "codigo",
            "nome",
            "descricao",
            "fabricante",
            "modelo",
            "numero_serie",
            "criticidade",
        ]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class PcpPlanoManutencaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PcpPlanoManutencao
        fields = ["nome", "tipo", "data_inicio", "intervalo_dias", "descricao"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "data_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class PcpEvidenciaManutencaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PcpEvidenciaManutencao
        fields = ["arquivo", "descricao"]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()
        self.fields["arquivo"].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png,.webp"


class PcpInicioManutencaoForm(BootstrapFormMixin, forms.Form):
    tipo = forms.ChoiceField(choices=TipoManutencao.choices, label="Tipo")
    programacao = forms.ModelChoiceField(
        queryset=PcpProgramacaoManutencao.objects.none(),
        required=False,
        label="Programação vinculada",
    )
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Observação")

    def __init__(self, *args: Any, ativo: PcpAtivo, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["programacao"].queryset = PcpProgramacaoManutencao.objects.select_related("plano").filter(
            plano__ativo_pcp=ativo,
            status=StatusManutencao.PLANEJADA,
        )
        self.aplicar_bootstrap()


class PcpConclusaoManutencaoForm(BootstrapFormMixin, forms.Form):
    data_fim = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="Data e hora de conclusão",
    )
    diagnostico = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Diagnóstico")
    servicos_executados = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Serviços executados")
    resultado = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Resultado")
    recomendacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Recomendações")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class PcpCorrecaoManutencaoForm(BootstrapFormMixin, forms.Form):
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Observação")
    diagnostico = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Diagnóstico")
    servicos_executados = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Serviços executados")
    resultado = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Resultado")
    recomendacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Recomendações")
    justificativa = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Justificativa da correção")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        execucao = kwargs.pop("execucao", None)
        super().__init__(*args, **kwargs)
        if execucao:
            self.fields["observacao"].initial = execucao.observacao
            self.fields["diagnostico"].initial = execucao.diagnostico
            self.fields["servicos_executados"].initial = execucao.servicos_executados
            self.fields["resultado"].initial = execucao.resultado
            self.fields["recomendacoes"].initial = execucao.recomendacoes
        self.aplicar_bootstrap()


class PcpJustificativaForm(BootstrapFormMixin, forms.Form):
    justificativa = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Justificativa")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class PcpAberturaParadaForm(BootstrapFormMixin, forms.Form):
    tipo = forms.ChoiceField(choices=TipoDowntime.choices, label="Tipo da parada")
    inicio = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="Data e hora de início",
    )
    motivo = forms.CharField(max_length=255, label="Motivo da parada")
    observacao = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Observação",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class PcpFechamentoParadaForm(BootstrapFormMixin, forms.Form):
    fim = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="Data e hora de encerramento",
    )
    observacao = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Observação final",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()
