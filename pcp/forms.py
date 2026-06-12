from __future__ import annotations

from typing import Any

from django import forms

from pcp.models import (
    CategoriaDowntime,
    PcpAtivo,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    StatusManutencao,
    TipoDowntime,
    TipoManutencao,
)


TIPOS_PARADA_AGRUPADOS = (
    (
        CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO.label,
        (
            (TipoDowntime.FALTA_MAO_OBRA, TipoDowntime.FALTA_MAO_OBRA.label),
            (TipoDowntime.MAQUINARIO_ESTRAGOU, TipoDowntime.MAQUINARIO_ESTRAGOU.label),
            (TipoDowntime.FALTA_MATERIAL, TipoDowntime.FALTA_MATERIAL.label),
            (TipoDowntime.MANUTENCAO, TipoDowntime.MANUTENCAO.label),
        ),
    ),
    (
        CategoriaDowntime.TEMPO_OCIOSO.label,
        ((TipoDowntime.FALTA_DESENHO, TipoDowntime.FALTA_DESENHO.label),),
    ),
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


class PcpEvidenciaManutencaoForm(BootstrapFormMixin, forms.Form):
    evidencia_problema = forms.FileField(
        required=False,
        label="Evidência do problema",
        help_text="Fotos, logs ou arquivos que demonstrem o problema antes da manutenção.",
    )
    descricao_problema = forms.CharField(
        required=False,
        max_length=255,
        label="Descrição do problema",
    )
    evidencia_solucao = forms.FileField(
        required=False,
        label="Evidência da solução / documentação",
        help_text="Fotos da solução, checklists, laudos ou documentação técnica.",
    )
    descricao_solucao = forms.CharField(
        required=False,
        max_length=255,
        label="Descrição da solução / documentação",
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()
        for nome_campo in ("evidencia_problema", "evidencia_solucao"):
            self.fields[nome_campo].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png,.webp"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if not cleaned_data.get("evidencia_problema") and not cleaned_data.get("evidencia_solucao"):
            raise forms.ValidationError("Selecione ao menos uma evidência para anexar.")
        if cleaned_data.get("descricao_problema") and not cleaned_data.get("evidencia_problema"):
            self.add_error("descricao_problema", "Envie a evidência do problema para usar esta descrição.")
        if cleaned_data.get("descricao_solucao") and not cleaned_data.get("evidencia_solucao"):
            self.add_error("descricao_solucao", "Envie a evidência da solução para usar esta descrição.")
        return cleaned_data


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
    tipo = forms.ChoiceField(
        choices=TIPOS_PARADA_AGRUPADOS,
        label="Tipo da parada",
        help_text="A categoria é definida automaticamente pelo tipo selecionado.",
    )
    inicio = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="Data e hora de início",
    )
    motivo = forms.CharField(max_length=255, label="Detalhamento da ocorrência")
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
