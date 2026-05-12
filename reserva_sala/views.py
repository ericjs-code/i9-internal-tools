from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from .forms import ReservaSalaForm
from .models import ReservaSala
from datetime import time as dtime, timedelta as dtimedelta
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError
from .services import _obter_mes_referencia, _deslocar_mes, _url_dashboard_paginada, _montar_calendario_reservas, MESES_PT


@login_required(login_url="/login/")
def reservas_sala_dashboard(request):
    ano, mes, hoje = _obter_mes_referencia(request)
    semanas, reservas_mes = _montar_calendario_reservas(ano, mes)
    reservas_todas = ReservaSala.objects.select_related("usuario").all().order_by("data", "horario_inicial")
    reservas_ativas = reservas_todas.filter(cancelada=False)
    reservas_canceladas = reservas_todas.filter(cancelada=True)
    proximas_reservas = reservas_ativas.filter(data__gte=hoje).order_by("data", "horario_inicial")[:8]

    # Pagination: 10 records per page
    paginator = Paginator(reservas_todas, 10)
    page = request.GET.get('page')
    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    try:
        reservas_page = paginator.page(page)
    except EmptyPage:
        reservas_page = paginator.page(paginator.num_pages)

    pagination = {
        "first_url": _url_dashboard_paginada(request, 1),
        "previous_url": _url_dashboard_paginada(request, reservas_page.previous_page_number()) if reservas_page.has_previous() else None,
        "next_url": _url_dashboard_paginada(request, reservas_page.next_page_number()) if reservas_page.has_next() else None,
        "last_url": _url_dashboard_paginada(request, paginator.num_pages),
    }

    ano_anterior, mes_anterior = _deslocar_mes(ano, mes, -1)
    ano_proximo, mes_proximo = _deslocar_mes(ano, mes, 1)
    context = {
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT[mes],
        "semanas": semanas,
        "reservas_mes": reservas_mes,
        "reservas_page": reservas_page,
        "paginator": paginator,
        "pagination": pagination,
        "nova_reserva_url": reverse("reserva_sala_nova"),
        "reservas_ativas": reservas_ativas,
        "reservas_canceladas": reservas_canceladas,
        "proximas_reservas": proximas_reservas,
        "mes_anterior": mes_anterior,
        "ano_anterior": ano_anterior,
        "mes_proximo": mes_proximo,
        "ano_proximo": ano_proximo,
        "total_reservas_mes": len(reservas_mes),
        "total_ativas": reservas_ativas.count(),
        "total_canceladas": reservas_canceladas.count(),
        "hoje": hoje,
    }
    return render(request, "reserva_sala/reservas_sala_dashboard.html", context)


@login_required(login_url="/login/")
def reserva_sala_nova(request):
    if request.method == "POST":
        form = ReservaSalaForm(request.POST)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.usuario = request.user
            # If recurring, generate a series id and attach to the original and copies
            serie_uuid = None
            if form.cleaned_data.get("recorrente_semanal"):
                serie_uuid = uuid.uuid4()
                reserva.serie = serie_uuid
            # Save the initial reservation (will run full_clean via model.save)
            reserva.save()

            # If recurrence requested, create additional weekly reservations
            created = 1
            skipped = 0
            if form.cleaned_data.get("recorrente_semanal"):
                weeks = form.cleaned_data.get("recorrencia_semanal_weeks") or 1
                # weeks includes the original week; create for subsequent (weeks-1)
                for wk in range(1, int(weeks)):
                    new_date = reserva.data + timedelta(weeks=wk)
                    nova = ReservaSala(
                        usuario=reserva.usuario,
                        data=new_date,
                        horario_inicial=reserva.horario_inicial,
                        horario_final=reserva.horario_final,
                        descricao=reserva.descricao,
                        cancelada=False,
                        recorrente_semanal=False,
                        recorrencia_semanal_weeks=0,
                        serie=serie_uuid,
                    )
                    try:
                        nova.full_clean()
                        nova.save()
                        created += 1
                    except ValidationError:
                        skipped += 1

            if skipped:
                messages.warning(request, f"Reserva criada. {created} registros gerados, {skipped} ignorados por conflito/validação.")
            else:
                messages.success(request, "Reserva criada com sucesso.")
            return redirect("reservas_sala_dashboard")
        messages.error(request, "Não foi possível salvar a reserva. Verifique os campos destacados.")
    else:
        form = ReservaSalaForm()
    return render(request, "reserva_sala/reserva_sala_form.html", {
        "form": form,
        "reserva": None,
        "titulo_pagina": "Nova Reserva de Sala",
        "usuario_logado": request.user,
        "dashboard_url": reverse("reservas_sala_dashboard"),
        "cancel_url": "",
        "reserva_form_js_url": "/static/js/reserva_sala/reserva_sala_form.js",
        "is_editing": False,
        "existing_start": "",
        "existing_end": "",
    })


@login_required(login_url="/login/")
def reserva_sala_editar(request, pk):
    reserva = get_object_or_404(ReservaSala, pk=pk)
    if request.method == "POST":
        form = ReservaSalaForm(request.POST, instance=reserva)
        if form.is_valid():
            apply_to_future = request.POST.get('apply_to_future') == '1'
            reserva_atualizada = form.save(commit=False)
            reserva_atualizada.usuario = reserva.usuario
            # If user chose to apply to future occurrences and there is a series id
            if apply_to_future and reserva.serie:
                updated = 0
                skipped = 0
                qs = ReservaSala.objects.filter(serie=reserva.serie, data__gte=reserva.data).order_by('data')
                for item in qs:
                    # Update each occurrence fields
                    item.horario_inicial = reserva_atualizada.horario_inicial
                    item.horario_final = reserva_atualizada.horario_final
                    item.descricao = reserva_atualizada.descricao
                    try:
                        item.full_clean()
                        item.save()
                        updated += 1
                    except ValidationError:
                        skipped += 1
                if skipped:
                    messages.warning(request, f"Atualização aplicada: {updated} registros atualizados, {skipped} ignorados por conflito/validação.")
                else:
                    messages.success(request, f"Atualização aplicada a {updated} agendamentos.")
            else:
                reserva_atualizada.save()
                messages.success(request, "Reserva atualizada com sucesso.")
            return redirect("reservas_sala_dashboard")
        messages.error(request, "Não foi possível atualizar a reserva. Verifique os campos destacados.")
    else:
        form = ReservaSalaForm(instance=reserva)
    return render(request, "reserva_sala/reserva_sala_form.html", {
        "form": form,
        "reserva": reserva,
        "titulo_pagina": "Editar Reserva de Sala",
        "usuario_logado": reserva.usuario,
        "dashboard_url": reverse("reservas_sala_dashboard"),
        "cancel_url": reverse("reserva_sala_cancelar", args=[reserva.pk]),
        "reserva_form_js_url": "/static/js/reserva_sala/reserva_sala_form.js",
        "is_editing": True,
        "existing_start": reserva.horario_inicial.strftime("%H:%M"),
        "existing_end": reserva.horario_final.strftime("%H:%M"),
    })


@login_required(login_url="/login/")
def reserva_sala_cancelar(request, pk):
    reserva = get_object_or_404(ReservaSala, pk=pk)
    if request.method == "POST":
        scope = request.POST.get('cancel_scope', 'this')
        if scope == 'future' and reserva.serie:
            # Cancel all occurrences in the series from this date forward
            qs = ReservaSala.objects.filter(serie=reserva.serie, data__gte=reserva.data, cancelada=False)
            count = qs.update(cancelada=True)
            if count:
                messages.success(request, f"{count} agendamentos cancelados com sucesso.")
            else:
                messages.info(request, "Nenhum agendamento futuro para cancelar.")
        else:
            if not reserva.cancelada:
                reserva.cancelada = True
                reserva.save()
                messages.success(request, "Reserva cancelada com sucesso.")
            else:
                messages.info(request, "Esta reserva já estava cancelada.")
        return redirect("reservas_sala_dashboard")
    return render(request, "reserva_sala/reserva_sala_confirmar_cancelamento.html", {"reserva": reserva})


@login_required(login_url="/login/")
def api_verificar_conflito_reserva(request):
    data_str = request.GET.get("data")
    inicio_str = request.GET.get("horario_inicial")
    final_str = request.GET.get("horario_final")
    reserva_id = request.GET.get("reserva_id")
    if not data_str or not inicio_str or not final_str:
        return JsonResponse({
            "conflito": False,
            "valido": False,
            "mensagem": "Informe data, horário inicial e horário final."
        }, status=400)
    try:
        data = datetime.strptime(data_str, "%Y-%m-%d").date()
        horario_inicial = datetime.strptime(inicio_str, "%H:%M").time()
        horario_final = datetime.strptime(final_str, "%H:%M").time()
    except ValueError:
        return JsonResponse({
            "conflito": False,
            "valido": False,
            "mensagem": "Formato de data ou horário inválido."
        }, status=400)
    if data < timezone.localdate():
        return JsonResponse({
            "conflito": True,
            "valido": False,
            "mensagem": "Não é permitido reservar uma data passada."
        })
    if horario_final <= horario_inicial:
        return JsonResponse({
            "conflito": True,
            "valido": False,
            "mensagem": "O horário final deve ser maior que o horário inicial."
        })

    # Verifica incrementos de 30 minutos
    if horario_inicial.minute % 30 != 0 or horario_final.minute % 30 != 0:
        return JsonResponse({
            "conflito": True,
            "valido": False,
            "mensagem": "Os horários devem estar em incrementos de 30 minutos (ex.: 13:00, 13:30)."
        })

    # Verifica duração mínima e múltipla de 30 minutos
    from datetime import timedelta
    duracao = (timedelta(hours=horario_final.hour, minutes=horario_final.minute) - timedelta(hours=horario_inicial.hour, minutes=horario_inicial.minute)).total_seconds() / 60
    if duracao < 30:
        return JsonResponse({
            "conflito": True,
            "valido": False,
            "mensagem": "A duração mínima da reserva é de 30 minutos."
        })
    if duracao % 30 != 0:
        return JsonResponse({
            "conflito": True,
            "valido": False,
            "mensagem": "A duração da reserva deve ser múltipla de 30 minutos."
        })
    conflito = ReservaSala.buscar_conflito(data, horario_inicial, horario_final, exclude_pk=reserva_id)
    if conflito:
        usuario_conflito = conflito.usuario.get_full_name() or conflito.usuario.username
        mensagem = (
            f"Conflito com reserva de {usuario_conflito}: "
            f"{conflito.horario_inicial.strftime('%H:%M')} às {conflito.horario_final.strftime('%H:%M')}."
        )
        return JsonResponse({
            "conflito": True,
            "valido": True,
            "mensagem": mensagem,
        })
    return JsonResponse({
        "conflito": False,
        "valido": True,
        "mensagem": "Horário disponível."
    })


@login_required(login_url="/login/")
def api_horarios_disponiveis(request):
    """Retorna slots de horários em incrementos de 30 minutos disponíveis para uma data.

    Response JSON:
    {
       "start_slots": ["08:00", "08:30", ...],
       "end_options": {"08:00": ["08:30","09:00", ...], ...}
    }
    """
    data_str = request.GET.get("data")
    reserva_id = request.GET.get("reserva_id")
    if not data_str:
        return JsonResponse({"mensagem": "Informe a data."}, status=400)
    try:
        data = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"mensagem": "Formato de data inválido."}, status=400)

    # Generate all 30-minute slots from 00:00 to 23:30
    slots = []
    for h in range(0, 24):
        for m in (0, 30):
            slots.append(dtime(hour=h, minute=m))

    # Fetch existing reservations on that date
    conflitos = ReservaSala.objects.filter(data=data, cancelada=False).order_by("horario_inicial")
    if reserva_id:
        conflitos = conflitos.exclude(pk=reserva_id)

    # Helper to check if a candidate time overlaps existing reservation
    def overlaps(candidate_start, candidate_end, reserva):
        return (candidate_start < reserva.horario_final) and (candidate_end > reserva.horario_inicial)

    # Build available start slots: a start is allowed if it doesn't fall inside an existing reservation
    start_slots = []
    end_options = {}
    for i, s in enumerate(slots):
        # skip starts in the past when date is today
        if data == timezone.localdate():
            now = timezone.localtime().time()
            if s <= now:
                continue
        inside = False
        for r in conflitos:
            if s >= r.horario_inicial and s < r.horario_final:
                inside = True
                break
        if inside:
            continue
        # compute max_end: the earliest reservation.horario_inicial that is after s, else 24:00
        max_end = dtime(hour=23, minute=59)
        for r in conflitos:
            if r.horario_inicial > s:
                max_end = r.horario_inicial
                break

        # collect end options: times > s, at least 30 minutes, and not overlapping next reservation
        ends = []
        for e in slots[i+1:]:
            # e must be <= max_end
            # treat max_end as exclusive (can't end after next reservation starts)
            if (dtime(hour=max_end.hour, minute=max_end.minute) <= e):
                break
            # duration at least 30
            duration_minutes = (dtimedelta(hours=e.hour, minutes=e.minute) - dtimedelta(hours=s.hour, minutes=s.minute)).total_seconds() / 60
            if duration_minutes >= 30 and duration_minutes % 30 == 0:
                ends.append(e.strftime("%H:%M"))
        if ends:
            start_slots.append(s.strftime("%H:%M"))
            end_options[s.strftime("%H:%M")] = ends

    return JsonResponse({"start_slots": start_slots, "end_options": end_options})