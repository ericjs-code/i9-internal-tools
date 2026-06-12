from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import group_required
from pcp.forms import (
    PcpAberturaParadaForm,
    PcpAtivoForm,
    PcpConclusaoManutencaoForm,
    PcpCorrecaoManutencaoForm,
    PcpEvidenciaManutencaoForm,
    PcpFechamentoParadaForm,
    PcpInicioManutencaoForm,
    PcpJustificativaForm,
    PcpPlanoManutencaoForm,
)
from pcp.models import (
    FinalidadeEvidencia,
    PcpAtivo,
    PcpDowntime,
    PcpEvidenciaManutencao,
    PcpExecucaoManutencao,
    PcpPlanoManutencao,
)
from pcp.selectors import (
    PcpDashboardSelector,
    agenda_manutencao,
    ativo_detalhado,
    ativos,
    execucao_detalhada,
    historico_manutencoes,
)
from pcp.services import (
    AtivoService,
    DowntimeService,
    EvidenciaManutencaoService,
    PlanoManutencaoService,
    ProgramacaoManutencaoService,
)
from pcp.services.exceptions import PcpConflictError, PcpValidationError


@login_required(login_url="/login/")
@group_required(["PCP"])
def dashboard_pcp(request: HttpRequest) -> HttpResponse:
    dias = _parse_periodo(request.GET.get("periodo"))
    context: dict[str, Any] = PcpDashboardSelector.get_context(dias=dias)
    return render(request, "pcp/dashboard.html", context)


@login_required(login_url="/login/")
@group_required(["PCP"])
def agenda(request: HttpRequest) -> HttpResponse:
    periodo = _parse_periodo_agenda(request.GET.get("periodo"))
    programacoes = agenda_manutencao(hoje=timezone.localdate(), periodo=periodo)
    return render(
        request,
        "pcp/agenda/lista.html",
        {"programacoes": programacoes, "periodo": periodo},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def historico(request: HttpRequest) -> HttpResponse:
    queryset = historico_manutencoes()
    busca = request.GET.get("q", "").strip()
    if busca:
        queryset = queryset.filter(
            Q(ativo_pcp__codigo__icontains=busca)
            | Q(ativo_pcp__nome__icontains=busca)
            | Q(programacao__plano__nome__icontains=busca)
            | Q(snapshot_ativo_codigo__icontains=busca)
            | Q(snapshot_ativo_nome__icontains=busca)
            | Q(snapshot_plano_nome__icontains=busca)
        )
    pagina = Paginator(queryset, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "pcp/historico/lista.html",
        {"execucoes": pagina, "page_obj": pagina, "busca": busca},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def listar_ativos(request: HttpRequest) -> HttpResponse:
    queryset = ativos()
    busca = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    criticidade = request.GET.get("criticidade", "").strip()
    if busca:
        queryset = queryset.filter(
            Q(codigo__icontains=busca) | Q(nome__icontains=busca) | Q(numero_serie__icontains=busca)
        )
    if status:
        queryset = queryset.filter(status=status)
    if criticidade:
        queryset = queryset.filter(criticidade=criticidade)
    return render(request, "pcp/ativos/lista.html", {"ativos": queryset, "filtros": request.GET})


@login_required(login_url="/login/")
@group_required(["PCP"])
def criar_ativo(request: HttpRequest) -> HttpResponse:
    form = PcpAtivoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ativo = AtivoService.criar_ativo(**form.cleaned_data)
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Ativo cadastrado com sucesso.")
            return redirect("pcp_detalhar_ativo", ativo_id=ativo.pk)
    return render(request, "pcp/ativos/form.html", {"form": form, "titulo": "Cadastrar ativo"})


@login_required(login_url="/login/")
@group_required(["PCP"])
def editar_ativo(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    form = PcpAtivoForm(request.POST or None, instance=ativo)
    if request.method == "POST" and form.is_valid():
        try:
            ativo = AtivoService.atualizar_ativo(ativo=ativo, **form.cleaned_data)
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Ativo atualizado com sucesso.")
            return redirect("pcp_detalhar_ativo", ativo_id=ativo.pk)
    return render(request, "pcp/ativos/form.html", {"form": form, "titulo": "Editar ativo", "ativo": ativo})


@login_required(login_url="/login/")
@group_required(["PCP"])
def detalhar_ativo(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    parada_aberta = DowntimeService.downtimes_abertos().filter(ativo_pcp=ativo).first()
    return render(
        request,
        "pcp/ativos/detalhe.html",
        {"ativo": ativo_detalhado(ativo_id=ativo.pk), "parada_aberta": parada_aberta},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def criar_plano(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    form = PcpPlanoManutencaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            plano = PlanoManutencaoService.criar_plano(ativo_pcp=ativo, **form.cleaned_data)
            _sincronizar_preventiva_visual(plano=plano)
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Plano de manutenção cadastrado com sucesso.")
            return redirect("pcp_detalhar_ativo", ativo_id=ativo.pk)
    return render(
        request,
        "pcp/planos/form.html",
        {"form": form, "titulo": f"Cadastrar plano - {ativo.codigo}", "ativo": ativo},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def editar_plano(request: HttpRequest, plano_id: int) -> HttpResponse:
    plano = get_object_or_404(PcpPlanoManutencao.objects.select_related("ativo_pcp"), pk=plano_id)
    form = PcpPlanoManutencaoForm(request.POST or None, instance=plano)
    if request.method == "POST" and form.is_valid():
        try:
            plano = PlanoManutencaoService.atualizar_plano(plano=plano, **form.cleaned_data)
            _sincronizar_preventiva_visual(plano=plano)
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Plano de manutenção atualizado com sucesso.")
            return redirect("pcp_detalhar_ativo", ativo_id=plano.ativo_pcp_id)
    return render(
        request,
        "pcp/planos/form.html",
        {"form": form, "titulo": f"Editar plano - {plano.ativo_pcp.codigo}", "ativo": plano.ativo_pcp, "plano": plano},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def desativar_plano(request: HttpRequest, plano_id: int) -> HttpResponse:
    plano = get_object_or_404(PcpPlanoManutencao.objects.select_related("ativo_pcp"), pk=plano_id)
    ativo_id = plano.ativo_pcp_id
    if request.method == "POST":
        try:
            PlanoManutencaoService.desativar_plano(plano=plano)
        except PcpConflictError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Plano de manutenção desativado com sucesso.")
    return redirect("pcp_detalhar_ativo", ativo_id=ativo_id)


@login_required(login_url="/login/")
@group_required(["PCP"])
def desativar_ativo(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    if request.method == "POST":
        try:
            AtivoService.desativar_ativo(ativo=ativo)
        except PcpConflictError as exc:
            messages.error(request, str(exc))
            return redirect("pcp_detalhar_ativo", ativo_id=ativo.pk)
        messages.success(request, "Ativo desativado com sucesso.")
    return redirect("pcp_listar_ativos")


@login_required(login_url="/login/")
@group_required(["PCP"])
def abrir_parada(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    form = PcpAberturaParadaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            DowntimeService.abrir_downtime(
                ativo_pcp=ativo,
                responsavel=request.user,
                **form.cleaned_data,
            )
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Parada registrada. O ativo agora está com status Parado.")
            return redirect("pcp_detalhar_ativo", ativo_id=ativo.pk)
    return render(
        request,
        "pcp/paradas/form.html",
        {"form": form, "ativo": ativo, "titulo": "Registrar parada"},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def fechar_parada(request: HttpRequest, downtime_id: int) -> HttpResponse:
    downtime = get_object_or_404(
        PcpDowntime.objects.select_related("ativo_pcp"),
        pk=downtime_id,
        fim__isnull=True,
    )
    form = PcpFechamentoParadaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            DowntimeService.fechar_downtime(downtime=downtime, **form.cleaned_data)
        except PcpValidationError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Parada encerrada e status operacional atualizado.")
            return redirect("pcp_detalhar_ativo", ativo_id=downtime.ativo_pcp_id)
    return render(
        request,
        "pcp/paradas/form.html",
        {"form": form, "ativo": downtime.ativo_pcp, "downtime": downtime, "titulo": "Encerrar parada"},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def iniciar_manutencao(request: HttpRequest, ativo_id: int) -> HttpResponse:
    ativo = get_object_or_404(PcpAtivo, pk=ativo_id)
    form = PcpInicioManutencaoForm(request.POST or None, ativo=ativo)
    if request.method == "POST" and form.is_valid():
        try:
            execucao = ProgramacaoManutencaoService.iniciar_execucao(
                ativo_pcp=ativo,
                responsavel=request.user,
                **form.cleaned_data,
            )
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Manutenção iniciada com sucesso.")
            return redirect("pcp_detalhar_execucao", execucao_id=execucao.pk)
    return render(
        request,
        "pcp/manutencoes/form.html",
        {"form": form, "titulo": f"Iniciar manutenção - {ativo.codigo}", "ativo": ativo},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def detalhar_execucao(request: HttpRequest, execucao_id: int) -> HttpResponse:
    execucao = get_object_or_404(PcpExecucaoManutencao, pk=execucao_id)
    return render(
        request,
        "pcp/manutencoes/detalhe.html",
        {"execucao": execucao_detalhada(execucao_id=execucao.pk), "evidencia_form": PcpEvidenciaManutencaoForm()},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def concluir_manutencao(request: HttpRequest, execucao_id: int) -> HttpResponse:
    execucao = get_object_or_404(PcpExecucaoManutencao, pk=execucao_id, data_fim__isnull=True)
    form = PcpConclusaoManutencaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            execucao = ProgramacaoManutencaoService.concluir_execucao(
                execucao=execucao,
                concluido_por=request.user,
                **form.cleaned_data,
            )
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Manutenção concluída e registrada no histórico.")
            return redirect("pcp_detalhar_execucao", execucao_id=execucao.pk)
    return render(
        request,
        "pcp/manutencoes/form.html",
        {"form": form, "titulo": f"Concluir manutenção - {execucao.ativo_pcp.codigo}", "execucao": execucao},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def corrigir_manutencao(request: HttpRequest, execucao_id: int) -> HttpResponse:
    if not request.user.has_perm("pcp.corrigir_execucao_concluida"):
        return HttpResponseForbidden("Usuário sem permissão para corrigir manutenção concluída.")
    execucao = get_object_or_404(PcpExecucaoManutencao, pk=execucao_id, data_fim__isnull=False)
    form = PcpCorrecaoManutencaoForm(request.POST or None, execucao=execucao)
    if request.method == "POST" and form.is_valid():
        try:
            execucao = ProgramacaoManutencaoService.corrigir_execucao_concluida(
                execucao=execucao,
                usuario=request.user,
                **form.cleaned_data,
            )
        except (PcpConflictError, PcpValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Correção documental registrada com sucesso.")
            return redirect("pcp_detalhar_execucao", execucao_id=execucao.pk)
    return render(
        request,
        "pcp/manutencoes/correcao.html",
        {"form": form, "execucao": execucao_detalhada(execucao_id=execucao.pk)},
    )


@login_required(login_url="/login/")
@group_required(["PCP"])
def adicionar_evidencia(request: HttpRequest, execucao_id: int) -> HttpResponse:
    execucao = get_object_or_404(PcpExecucaoManutencao, pk=execucao_id)
    if request.method == "POST":
        form = PcpEvidenciaManutencaoForm(request.POST, request.FILES)
        if form.is_valid():
            arquivos: list[tuple[UploadedFile, str, str]] = []
            if form.cleaned_data.get("evidencia_problema"):
                arquivos.append(
                    (
                        form.cleaned_data["evidencia_problema"],
                        form.cleaned_data["descricao_problema"],
                        FinalidadeEvidencia.PROBLEMA,
                    )
                )
            if form.cleaned_data.get("evidencia_solucao"):
                arquivos.append(
                    (
                        form.cleaned_data["evidencia_solucao"],
                        form.cleaned_data["descricao_solucao"],
                        FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO,
                    )
                )
            try:
                evidencias = EvidenciaManutencaoService.adicionar_multiplas(
                    execucao=execucao,
                    arquivos=arquivos,
                    usuario=request.user,
                )
            except (PcpConflictError, PcpValidationError) as exc:
                messages.error(request, str(exc))
            else:
                quantidade = len(evidencias)
                messages.success(
                    request,
                    f"{quantidade} evidência{'s' if quantidade != 1 else ''} adicionada{'s' if quantidade != 1 else ''} com sucesso.",
                )
        else:
            for erros in form.errors.values():
                for erro in erros:
                    messages.error(request, erro)
    return redirect("pcp_detalhar_execucao", execucao_id=execucao.pk)


@login_required(login_url="/login/")
@group_required(["PCP"])
def desativar_evidencia(request: HttpRequest, evidencia_id: int) -> HttpResponse:
    if not request.user.has_perm("pcp.desativar_evidencia_manutencao"):
        return HttpResponseForbidden("Usuário sem permissão para desativar evidência.")
    evidencia = get_object_or_404(PcpEvidenciaManutencao, pk=evidencia_id)
    execucao_id = evidencia.execucao_id
    if request.method == "POST":
        form = PcpJustificativaForm(request.POST)
        if form.is_valid():
            try:
                EvidenciaManutencaoService.desativar(
                    evidencia=evidencia,
                    usuario=request.user,
                    justificativa=form.cleaned_data["justificativa"],
                )
            except (PcpConflictError, PcpValidationError) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Evidência desativada com sucesso.")
        else:
            messages.error(request, "Informe a justificativa para desativar a evidência.")
    return redirect("pcp_detalhar_execucao", execucao_id=execucao_id)


@login_required(login_url="/login/")
@group_required(["PCP"])
def baixar_evidencia(request: HttpRequest, evidencia_id: int) -> FileResponse:
    evidencia = get_object_or_404(PcpEvidenciaManutencao, pk=evidencia_id)
    arquivo = evidencia.arquivo.open("rb")
    return FileResponse(
        arquivo,
        as_attachment=True,
        filename=evidencia.nome_original,
        content_type=evidencia.tipo_mime,
    )


def _parse_periodo(periodo: str | None) -> int:
    if periodo in {"7", "30", "90", "180", "365"}:
        return int(periodo)
    return 90


def _parse_periodo_agenda(periodo: str | None) -> str:
    if periodo in {"atrasadas", "hoje", "7", "15", "30", "90", "180", "365"}:
        return periodo
    return "90"


def _sincronizar_preventiva_visual(*, plano: PcpPlanoManutencao) -> None:
    ProgramacaoManutencaoService.sincronizar_preventiva_do_plano(plano=plano)
