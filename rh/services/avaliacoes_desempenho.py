from core.models import PerfilOrganizacional
from core.services.permissoes_organizacionais import (
    setores_gerenciados_por,
    usuario_eh_gestor,
    usuario_tem_acesso_global,
)
from rh.models import AvaliacaoDesempenho


def avaliacoes_visiveis_para(user):
    qs = AvaliacaoDesempenho.objects.select_related(
        'avaliado',
        'avaliada_por',
        'usuario_ciencia_gestor',
        'usuario_ciencia_colaborador',
    ).prefetch_related('notas__competencia')

    if not user or not user.is_authenticated:
        return qs.none()

    if usuario_tem_acesso_global(user):
        return qs

    if usuario_eh_gestor(user):
        return qs.filter(
            avaliado__perfil_organizacional__setor__in=setores_gerenciados_por(user),
            avaliado__perfil_organizacional__ativo=True,
        )

    return qs.filter(avaliado=user)


def pode_criar_avaliacao(user):
    return usuario_tem_acesso_global(user) or usuario_eh_gestor(user)


def pode_editar_avaliacao(user, avaliacao):
    if usuario_tem_acesso_global(user):
        return True

    if not user or not user.is_authenticated:
        return False

    if avaliacao.ciencia_gestor and avaliacao.ciencia_colaborador:
        return False

    if not usuario_eh_gestor(user):
        return False

    return PerfilOrganizacional.objects.filter(
        usuario=avaliacao.avaliado,
        setor__in=setores_gerenciados_por(user),
        ativo=True,
    ).exists()


def pode_dar_ciencia_gestor(user, avaliacao):
    if usuario_tem_acesso_global(user):
        return True

    if not user or not user.is_authenticated:
        return False

    if not usuario_eh_gestor(user):
        return False

    return PerfilOrganizacional.objects.filter(
        usuario=avaliacao.avaliado,
        setor__in=setores_gerenciados_por(user),
        ativo=True,
    ).exists()


def pode_dar_ciencia_colaborador(user, avaliacao):
    return bool(
        user
        and user.is_authenticated
        and avaliacao
        and avaliacao.avaliado_id == user.id
        and avaliacao.ciencia_gestor
    )


def pode_visualizar_resultado_avaliacao(user, avaliacao):
    if not user or not user.is_authenticated or not avaliacao:
        return False

    if usuario_tem_acesso_global(user):
        return True

    if usuario_eh_gestor(user):
        if PerfilOrganizacional.objects.filter(
            usuario=avaliacao.avaliado,
            setor__in=setores_gerenciados_por(user),
            ativo=True,
        ).exists():
            return True

    if avaliacao.avaliado_id == user.id:
        return avaliacao.ciencia_gestor is True

    return False


def preencher_snapshot_avaliacao(avaliacao):
    avaliado = avaliacao.avaliado
    perfil = getattr(avaliado, 'perfil_organizacional', None)

    avaliacao.nome_avaliado = avaliado.get_full_name() or avaliado.username
    if perfil:
        avaliacao.cargo_avaliado = perfil.cargo
        avaliacao.setor_avaliado = perfil.setor.nome if perfil.setor else ''
        avaliacao.data_admissao_avaliado = perfil.data_admissao

    return avaliacao
