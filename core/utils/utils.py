import pandas as pd
from datetime import timedelta

def converter_horas(valor_excel):
    if pd.isna(valor_excel) or str(valor_excel).strip() == '':
        return None
    try:
        tempo_str = str(valor_excel).strip()
        partes = tempo_str.split(':')
        return timedelta(hours=int(partes[0]), minutes=int(partes[1]), seconds=int(partes[2]))
    except Exception:
        return None