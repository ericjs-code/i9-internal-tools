import pandas as pd
from datetime import timedelta
from django.core.management.base import BaseCommand
from rh.models import Funcionario, RegistroAbsenteismo


class Command(BaseCommand):
    help = 'Importa a planilha de ponto/absenteísmo'

    # Função para converter o texto do Excel em Tempo do Python
    def converter_horas(self, valor_excel):
        if pd.isna(valor_excel) or str(valor_excel).strip() == '':
            return None

        try:
            tempo_str = str(valor_excel).strip()
            partes = tempo_str.split(':')
            horas = int(partes[0])
            minutos = int(partes[1])
            seconds = int(partes[2])
            return timedelta(hours=horas, minutes=minutos, seconds=int(partes[2]))

        except Exception as e:
            return None

    def handle(self, *args, **kwargs):
        caminho_arquivo = r"C:\Users\vmart\Downloads\relatorio_2026421_1438.CSV"

        data_ref = '2026-04-01'

        self.stdout.write(self.style.WARNING('Lendo planilha de ponto...'))

        try:
            df = pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8-sig', dtype=str)
            df.columns = df.columns.str.strip()
            self.stdout.write(self.style.WARNING(f"Colunas encontradas: {df.columns.tolist()}"))
            sucesso = 0
            erros_matricula = 0

            for index, row in df.iterrows():
                matricula_excel = str(row['Cod Epr']).replace('.0', '').strip()

                funcionario_obj = Funcionario.objects.filter(matricula=matricula_excel).first() # Busca o funcionario no banco pela matricula
                if not funcionario_obj:
                    erros_matricula += 1
                    continue

                horas_normais_convertidas = self.converter_horas(row['Total Normais'])
                horas_faltas_convertidas = self.converter_horas(row['Falta e Atraso'])
                horas_extras_convertidas = self.converter_horas(row['Extra Diurna'])
                abono_convertido = self.converter_horas(row['Abono'])

                RegistroAbsenteismo.objects.update_or_create(
                    funcionario=funcionario_obj,
                    data_referencia=data_ref,
                    defaults={
                        'horas_normais': horas_normais_convertidas,
                        'horas_falta': horas_faltas_convertidas,
                        'horas_extras': horas_extras_convertidas,
                        'abono': abono_convertido
                    }
                )

                sucesso += 1

            self.stdout.write(self.style.SUCCESS(f'Sucesso! {sucesso} registros salvos.'))
            if erros_matricula > 0:
                self.stdout.write(self.style.WARNING(
                    f'Aviso: {erros_matricula} funcionários não encontrados no banco pela matrícula.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro: {str(e)}'))