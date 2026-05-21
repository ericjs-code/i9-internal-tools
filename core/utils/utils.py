import pandas as pd
from datetime import timedelta

def convert_hours(valor_excel):
    if pd.isna(valor_excel) or str(valor_excel).strip() == '':
        return None
    try:
        tempo_str = str(valor_excel).strip()
        partes = tempo_str.split(':')
        return timedelta(hours=int(partes[0]), minutes=int(partes[1]), seconds=int(partes[2]))
    except Exception:
        return None

def formata_dt(data_obj):
    return data_obj.strftime('%d/%m/%Y') if data_obj else '-'