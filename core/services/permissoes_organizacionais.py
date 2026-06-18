from django.contrib.auth import get_user_model
from django.db.models import F, Q

from core.models import SetorOrganizacional


GRUPOS_ACESSO_GLOBAL = {'RH', 'TI', 'Diretoria'}


def _vinculos_avaliacao_model():
    from rh.models import VinculoAvaliacaoDesempenho

    return VinculoAvaliacaoDesempenho


def _vinculos_validos_do_gestor(user):
    VinculoAvaliacaoDesempenho = _vinculos_avaliacao_model()
    return VinculoAvaliacaoDesempenho.objects.filter(
        ativo=True,
        gestor_usuario=user,
        avaliado__usuario__isnull=False,
    ).exclude(
        avaliado__usuario=user,
    ).filter(
        Q(setor_gestor__isnull=True)
        | Q(setor_gestor='')
        | Q(setor_avaliado=F('setor_gestor'))
    )


def usuarios_vinculados_avaliacao_ids(user):
    if not user or not user.is_authenticated:
        return []

    return list(
        _vinculos_validos_do_gestor(user).values_list('avaliado__usuario_id', flat=True).distinct()
    )


def usuario_tem_acesso_global(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    grupos = set(user.groups.values_list('name', flat=True))
    return bool(grupos.intersection(GRUPOS_ACESSO_GLOBAL))


def usuario_eh_gestor(user):
    if not user or not user.is_authenticated:
        return False

    return user.setores_gestor.filter(ativo=True).exists() or _vinculos_validos_do_gestor(user).exists()


def setores_gerenciados_por(user):
    if not user or not user.is_authenticated:
        return SetorOrganizacional.objects.none()

    codigos_vinculos = _vinculos_validos_do_gestor(user).values_list('setor_avaliado', flat=True)

    return SetorOrganizacional.objects.filter(
        Q(codigo__in=codigos_vinculos)
        | Q(
            gestores__gestor=user,
            gestores__ativo=True,
        )
    ).filter(
        ativo=True,
    ).distinct()


def usuario_pode_ver_usuario(user, usuario_alvo):
    if not user or not user.is_authenticated or not usuario_alvo:
        return False

    if usuario_tem_acesso_global(user):
        return True

    if user == usuario_alvo:
        return True

    return usuario_alvo.pk in usuarios_vinculados_avaliacao_ids(user)


def usuarios_visiveis_para(user):
    User = get_user_model()

    if not user or not user.is_authenticated:
        return User.objects.none()

    base = User.objects.filter(is_active=True, perfil_organizacional__ativo=True)

    if usuario_tem_acesso_global(user):
        return base.distinct().order_by('first_name', 'last_name', 'username')

    ids_vinculados = usuarios_vinculados_avaliacao_ids(user)
    if ids_vinculados:
        return base.filter(Q(pk=user.pk) | Q(pk__in=ids_vinculados)).distinct().order_by(
            'first_name',
            'last_name',
            'username',
        )

    return base.filter(pk=user.pk).distinct()


def usuarios_avaliaveis_para(user):
    User = get_user_model()

    if not user or not user.is_authenticated:
        return User.objects.none()

    base = User.objects.filter(
        is_active=True,
        perfil_organizacional__ativo=True,
        perfil_organizacional__pode_ser_avaliado=True,
    ).select_related(
        'perfil_organizacional',
        'perfil_organizacional__setor',
    )

    if usuario_tem_acesso_global(user):
        return base.exclude(pk=user.pk).distinct().order_by('first_name', 'last_name', 'username')

    ids_vinculados = usuarios_vinculados_avaliacao_ids(user)
    if ids_vinculados:
        return base.filter(pk__in=ids_vinculados).exclude(pk=user.pk).distinct().order_by(
            'first_name',
            'last_name',
            'username',
        )

    return User.objects.none()
