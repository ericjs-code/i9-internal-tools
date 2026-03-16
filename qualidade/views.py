from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required(login_url='/login/')
def dashboard_qualidade(request):
    return render(request, 'qualidade/dashboard.html')