from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import group_required
from pcp.forms import (
    PcpAtivoForm,
    PcpConclusaoManutencaoForm,
    PcpEvidenciaManutencaoForm,
    PcpInicioManutencaoForm,
)
from pcp.models import PcpAtivo, PcpEvidenciaManutencao, PcpExecucaoManutencao
from pcp.selectors import PcpDashboardSelector, ativo_detalhado, ativos, execucao_detalhada
from pcp.services import AtivoService, EvidenciaManutencaoService, ProgramacaoManutencaoService
from pcp.services.exceptions import PcpConflictError, PcpValidationError


@login_required(login_url="/login/")
@group_required(["PCP"])
def dashboard_pcp(request: HttpRequest) -> HttpResponse:
    dias = _parse_periodo(request.GET.get("periodo"))
    context: dict[str, Any] = PcpDashboardSelector.get_context(dias=dias)
    return render(request, "pcp/dashboard.html", context)


@login_required(login_url="/login/")
@group_required(["PCP"])
def listar_ativos(request: HttpRequest) -> HttpResponse:
    queryset = ativos()
    busca = request.GET.get("q", "").strip()
    area = request.GET.get("area", "").strip()
    status = request.GET.get("status", "").strip()
    criticidade = request.GET.get("criticidade", "").strip()
    if busca:
        queryset = queryset.filter(
            Q(codigo__icontains=busca) | Q(nome__icontains=busca) | Q(numero_serie__icontains=busca)
        )
    if area:
        queryset = queryset.filter(area_id=area)
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
    return render(request, "pcp/ativos/detalhe.html", {"ativo": ativo_detalhado(ativo_id=ativo.pk)})


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
def adicionar_evidencia(request: HttpRequest, execucao_id: int) -> HttpResponse:
    execucao = get_object_or_404(PcpExecucaoManutencao, pk=execucao_id)
    if request.method == "POST":
        form = PcpEvidenciaManutencaoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                EvidenciaManutencaoService.adicionar(
                    execucao=execucao,
                    arquivo=form.cleaned_data["arquivo"],
                    descricao=form.cleaned_data["descricao"],
                    usuario=request.user,
                )
            except (PcpConflictError, PcpValidationError) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Evidência adicionada com sucesso.")
    return redirect("pcp_detalhar_execucao", execucao_id=execucao.pk)


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
    if periodo in {"7", "30", "90"}:
        return int(periodo)
    return 30
