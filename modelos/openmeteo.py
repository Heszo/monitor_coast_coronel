"""
Oleaje de ECMWF WAM, NOAA GFS-Wave y DWD GWAM desde Open-Meteo Marine (uso no comercial).

Una consulta por modelo con start_date/end_date: entrega la serie archivada (pronósticos de corto
plazo encadenados) y el pronóstico vigente. `cell_selection=sea` elige la celda de mar más cercana;
en Coronel las tres caen en (-37,0; -73,25), ~8,5 km mar afuera. Variables que faltan en un modelo
(p. ej. el periodo peak de GFS-Wave y GWAM) vienen vacías y se descartan.
"""
import time

import pandas as pd
import requests

from catalogo import BOYA
from modelos.extrae import distancia_km

URL = "https://marine-api.open-meteo.com/v1/marine"
UA = {"User-Agent": "monitor-coronel MetGeo (divulgacion no comercial)"}
MODELOS = {"ecmwf_wam": "ecmwf_wam025", "gfswave": "ncep_gfswave025", "gwam": "dwd_gwam"}
VARS = {"wave_height": "hs", "wave_peak_period": "tp", "wave_period": "tm", "wave_direction": "dm"}
FUTURO = 10  # días


def lee(modelo, inicio, fin=None, intentos=4):
    fin = fin or pd.Timestamp.now(tz="UTC").tz_localize(None) + pd.Timedelta(days=FUTURO)
    p = dict(latitude=BOYA["lat"], longitude=BOYA["lon"], hourly=",".join(VARS), models=MODELOS[modelo],
             start_date=f"{pd.Timestamp(inicio):%Y-%m-%d}", end_date=f"{pd.Timestamp(fin):%Y-%m-%d}",
             cell_selection="sea", timezone="GMT")
    for k in range(intentos):
        r = requests.get(URL, params=p, headers=UA, timeout=120)
        if r.status_code == 400 and "end_date" in r.text and k < intentos - 1:
            fin -= pd.Timedelta(days=3)  # el horizonte del modelo es más corto
            p["end_date"] = f"{fin:%Y-%m-%d}"
            continue
        if r.status_code in (429, 502, 503, 504) and k < intentos - 1:
            time.sleep(15 * (k + 1))
            continue
        r.raise_for_status()
        break
    j = r.json()
    h = j["hourly"]
    df = pd.DataFrame({VARS[k]: h[k] for k in VARS if k in h}, index=pd.DatetimeIndex(pd.to_datetime(h["time"]), name="time"))
    df = df.dropna(axis=1, how="all").dropna(how="all").astype("float32")
    celda = [j["latitude"], j["longitude"]]
    return df, dict(metodo="servidor", celda=celda, dataset=f"Open-Meteo {MODELOS[modelo]}",
                    distancia_km=round(float(distancia_km(BOYA["lat"], BOYA["lon"], *celda)), 1))
