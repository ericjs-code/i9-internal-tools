from __future__ import annotations

from typing import Any

from django import forms

from pcp.models import (
    PcpAtivo,
    PcpEvidenciaManutencao,
    PcpProgramacaoManutencao,
    StatusManutencao,
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
            "area",
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
