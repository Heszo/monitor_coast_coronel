"""
HYCOM ESPC-D-V02 (US Navy, 1/25°, 3-horario) desde el THREDDS de hycom.org.

El dataset FMRC "best" junta las corridas recientes: ~7 días hacia atrás y 16 días de pronóstico
(el servidor no guarda más historia de uv3z): la historia se arma acumulando cada ingesta.
Se pide la ventana alrededor de la boya por NCSS (un netCDF chico, una sola consulta). El servidor a
veces responde 500 "Stale file handle" (le pasó todo el 04/10/2026, también por OPeNDAP): se reintenta
y, si sigue, se informa el error sin detener la ingesta. No se usa OPeNDAP de respaldo porque una
lectura colgada no respeta ningún timeout.
"""
import io
import time

import numpy as np
import pandas as pd
import requests
import xarray as xr

from catalogo import BOYA
from modelos import con_rapidez
from modelos.extrae import punto_uv

NCSS = "https://ncss.hycom.org/thredds/ncss/FMRC_ESPC-D-V02_uv3z/FMRC_ESPC-D-V02_uv3z_best.ncd"
CAJA = 0.15  # ° (a 1/25° son ±4 celdas)
UA = {"User-Agent": "monitor-coronel MetGeo (divulgacion no comercial)"}


def _normaliza(ds):
    ds = ds.rename({k: v for k, v in (("lat", "latitude"), ("lon", "longitude")) if k in ds.dims})
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    if float(ds.longitude.max()) > 180:
        ds = ds.assign_coords(longitude=((ds.longitude + 180) % 360) - 180)
    return ds.sortby(["latitude", "longitude"])


def por_ncss(intentos=3):
    p = dict(var=["water_u", "water_v"], north=BOYA["lat"] + CAJA, south=BOYA["lat"] - CAJA,
             west=BOYA["lon"] - CAJA, east=BOYA["lon"] + CAJA, horizStride=1, temporal="all", vertCoord=0,
             accept="netcdf")
    ultimo = ""
    for k in range(intentos):
        r = requests.get(NCSS, params=p, headers=UA, timeout=(30, 240))
        if r.ok and r.content[:3] in (b"CDF", b"\x89HD"):
            return xr.open_dataset(io.BytesIO(r.content)).load()
        ultimo = f"HTTP {r.status_code}: {r.text[:80]}"
        time.sleep(10 * (k + 1))
    raise RuntimeError(f"NCSS de HYCOM: {ultimo}")


def lee(inicio=None, fin=None):
    ds = _normaliza(por_ncss())
    u, v, info = punto_uv(ds["water_u"], ds["water_v"], BOYA["lat"], BOYA["lon"])
    df = pd.DataFrame({"u": u, "v": v}, index=pd.DatetimeIndex(pd.to_datetime(ds.time.values), name="time"))
    df = con_rapidez(df.dropna(how="all")).astype("float32")
    if inicio is not None:
        df = df[df.index >= pd.Timestamp(inicio)]
    return df, dict(info, dataset="FMRC_ESPC-D-V02_uv3z (best)", corrida=str(ds.attrs.get("time_origin", "")))
