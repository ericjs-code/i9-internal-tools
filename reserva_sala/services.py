import calendar
from collections import defaultdict
from django.urls import reverse
from django.utils import timezone
from .models import ReservaSala

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

def _obter_mes_referencia(request):
    hoje = timezone.localdate()
    try:
        ano = int(request.GET.get("ano", hoje.year))
    except (TypeError, ValueError):
        ano = hoje.year
    try:
        mes = int(request.GET.get("mes", hoje.month))
    except (TypeError, ValueError):
        mes = hoje.month
    if mes < 1 or mes > 12:
        mes = hoje.month
    return ano, mes, hoje

def _deslocar_mes(ano, mes, delta):
    mes_total = mes + delta
    ano += (mes_total - 1) // 12
    mes_total = ((mes_total - 1) % 12) + 1
    return ano, mes_total

def _url_dashboard_paginada(request, page):
    params = request.GET.copy()
    params["page"] = str(page)
    query = params.urlencode()
    return f"{reverse('reservas_sala_dashboard')}?{query}#reservas-list" if query else f"{reverse('reservas_sala_dashboard')}#reservas-list"

def _montar_calendario_reservas(ano, mes):
    reservas = list(
        ReservaSala.objects.select_related("usuario")
        .filter(data__year=ano, data__month=mes)
        .order_by("data", "horario_inicial")
    )
    reservas_por_dia = defaultdict(list)
    for reserva in reservas:
        if reserva.cancelada:
            reserva.card_class = "bg-secondary-subtle text-muted"
            reserva.badge_class = "text-bg-secondary"
            reserva.status_label = "Cancelada"
        else:
            reserva.card_class = "bg-primary-subtle"
            reserva.badge_class = "text-bg-primary"
            reserva.status_label = "Reservada"
        reservas_por_dia[reserva.data].append(reserva)
    semanas = []
    calendario = calendar.Calendar(firstweekday=0)
    for semana in calendario.monthdatescalendar(ano, mes):
        dias_semana = []
        for dia in semana:
            day_card_class = "border rounded-3 p-2 h-100 bg-white"
            if dia.month != mes:
                day_card_class = "border rounded-3 p-2 h-100 bg-light text-muted"
            day_number_class = "fw-bold text-primary" if dia == timezone.localdate() else "fw-bold"
            dias_semana.append({
                "data": dia,
                "no_mes": dia.month == mes,
                "card_class": day_card_class,
                "day_number_class": day_number_class,
                "reservas": reservas_por_dia.get(dia, []),
            })
        semanas.append(dias_semana)
    return semanas, reservas