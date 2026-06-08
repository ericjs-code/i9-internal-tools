import json
from functools import lru_cache
from pathlib import Path


UF_CHOICES = [
    ('AC', 'AC'), ('AL', 'AL'), ('AP', 'AP'), ('AM', 'AM'), ('BA', 'BA'), ('CE', 'CE'),
    ('DF', 'DF'), ('ES', 'ES'), ('GO', 'GO'), ('MA', 'MA'), ('MT', 'MT'), ('MS', 'MS'),
    ('MG', 'MG'), ('PA', 'PA'), ('PB', 'PB'), ('PR', 'PR'), ('PE', 'PE'), ('PI', 'PI'),
    ('RJ', 'RJ'), ('RN', 'RN'), ('RS', 'RS'), ('RO', 'RO'), ('RR', 'RR'), ('SC', 'SC'),
    ('SP', 'SP'), ('SE', 'SE'), ('TO', 'TO'),
]


@lru_cache(maxsize=1)
def get_municipios_brasileiros_choices():
    caminho = Path(__file__).resolve().parent / 'data_cities' / 'municipios_brasil.json'
    with caminho.open(encoding='utf-8-sig') as arquivo:
        municipios = json.load(arquivo)
    return [(municipio['valor'], municipio['label']) for municipio in municipios]


ORGAOS_EXPEDIDORES_RG = [
    ('SSP', 'SSP - Secretaria de Segurança Pública'),
    ('SESP', 'SESP - Secretaria de Estado de Segurança Pública'),
    ('SESPAP', 'SESPAP - Secretaria de Estado de Segurança Pública e Administração Penitenciária'),
    ('GEJSPC', 'GEJSPC - Gerência de Estado de Justiça, Segurança Pública e Cidadania'),
    ('PC', 'PC - Polícia Civil'),
    ('PCMG', 'PCMG - Polícia Civil do Estado de Minas Gerais'),
    ('PCEMG', 'PCEMG - Polícia Civil do Estado de Minas Gerais'),
    ('SSPPC', 'SSPPC - SSP / Polícia Civil'),
    ('DETRAN', 'DETRAN - Departamento Estadual de Trânsito'),
    ('DPF', 'DPF - Departamento de Polícia Federal'),
    ('SEJUSP', 'SEJUSP - Secretaria de Estado de Justiça e Segurança Pública'),
    ('SEJSP', 'SEJSP - Secretaria de Estado de Justiça e Segurança Pública'),
    ('SGPC', 'SGPC - Superintendência Geral de Polícia Civil'),
    ('CPP', 'CPP - Centro de Perícias do Paraná'),
    ('SDS', 'SDS - Secretaria de Defesa Social'),
    ('SECC', 'SECC - Secretaria de Estado da Casa Civil'),
    ('DGPC', 'DGPC - Diretoria Geral da Polícia Civil'),
    ('SEJUSO', 'SEJUSO - Secretaria de Estado de Justiça e Segurança Pública'),
    ('SJS', 'SJS - Secretaria da Justiça e Segurança'),
    ('SJTC', 'SJTC - Secretaria da Justiça do Trabalho e Cidadania'),
    ('SJTS', 'SJTS - Secretaria da Justiça do Trabalho e Segurança'),
    ('SPTC', 'SPTC - Secretaria de Polícia Técnico-Científica'),
    ('MTE', 'MTE - Ministério do Trabalho e Emprego'),
    ('MMA', 'MMA - Ministério da Marinha'),
    ('MEX', 'MEX - Ministério do Exército'),
    ('MAE', 'MAE - Ministério da Aeronáutica'),
    ('SESDC', 'SESDC - Secretaria de Estado da Segurança, Defesa e Cidadania'),
]
