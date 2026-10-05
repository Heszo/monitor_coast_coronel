"""
RTOFS Global (NOAA NCEP, HYCOM 1/12°) desde el bucket abierto de AWS (noaa-nws-rtofs-pds).

En acceso abierto, la única corriente global en netCDF es la BAROTRÓPICA (u/v_barotropic_velocity
de rtofs_glo_2ds_*_diag.nc, promedio en la columna); la de superficie viene en archivos .tgz de
437 MB. Se compara igual, como referencia, y se rotula así en la app.

Cada archivo es un HDF5 global de ~195 MB, troceado en bloques de 825×1125: se leen por rangos HTTP
solo la ventana de 7×7 celdas alrededor de la boya (~2 s por archivo). Día D:
- nowcast n000…n024 = D-1 00z … D 00z (se usa cada 3 h);
- pronóstico f000…f192 desde D 00z (se usa cada 6 h hasta 120 h: ~6 s por archivo).
En esta latitud la grilla es Mercator (lat solo depende de Y, lon de X): la ventana es regular.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

import almacen
from catalogo import BOYA
from modelos import con_rapidez
from modelos.extrae import punto_uv

S3 = "https://noaa-nws-rtofs-pds.s3.amazonaws.com"
R = 3  # celdas a cada lado
HILOS = 8
NOWCAST = [f"n{h:03d}" for h in range(3, 25, 3)]
PRONOSTICO = [f"f{h:03d}" for h in range(6, 121, 6)]


def _url(dia, paso):
    return f"{S3}/rtofs.{dia:%Y%m%d}/rtofs_glo_2ds_{paso}_diag.nc"


def _abre(url):
    import fsspec
    import h5py
    f = fsspec.filesystem("https").open(url, block_size=2 ** 18, cache_type="readahead")
    return h5py.File(f, "r")


def indice(base=None):
    """(Y, X) de la celda más cercana a la boya; se calcula una vez (lee 2 × 59 MB) y se guarda."""
    f = almacen.DATOS if base is None else base
    ruta = f / "modelos" / "rtofs_indice.json"
    if ruta.exists():
        return json.loads(ruta.read_text())
    dia = ultimo_dia()
    with _abre(_url(dia, "n024")) as h:
        lat, lon = h["Latitude"][:], h["Longitude"][:]
    lon = ((lon + 180) % 360) - 180
    y, x = np.unravel_index(((lat - BOYA["lat"]) ** 2 + (lon - BOYA["lon"]) ** 2).argmin(), lat.shape)
    out = dict(y=int(y), x=int(x), lats=lat[y - R:y + R + 1, x].round(5).tolist(),
               lons=lon[y, x - R:x + R + 1].round(5).tolist())
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(out))
    return out


def ultimo_dia(hoy=None):
    """El último día con el pronóstico completo publicado (f192)."""
    import requests
    hoy = (hoy or pd.Timestamp.now(tz="UTC").tz_localize(None)).floor("D")
    for k in range(4):
        d = hoy - pd.Timedelta(days=k)
        if requests.head(_url(d, "f192"), timeout=30).ok:
            return d
    raise RuntimeError("RTOFS: sin corridas completas en los últimos 4 días")


def _lee_archivo(url, idx):
    """(tiempo, u[7×7], v[7×7]) o None si el archivo no existe."""
    try:
        with _abre(url) as h:
            y, x = idx["y"], idx["x"]
            sl = (0, slice(y - R, y + R + 1), slice(x - R, x + R + 1))
            u, v = h["u_barotropic_velocity"][sl], h["v_barotropic_velocity"][sl]
            t = pd.Timestamp("1900-12-31") + pd.Timedelta(days=float(h["MT"][0]))  # MT: días desde 1900-12-31
    except (FileNotFoundError, OSError):
        return None
    u, v = np.where(np.abs(u) > 1e3, np.nan, u), np.where(np.abs(v) > 1e3, np.nan, v)
    return t.round("h"), u, v


def lee(inicio, fin=None, base=None, log=print):
    idx = indice(base)
    dia_f = ultimo_dia()
    dias = pd.date_range(pd.Timestamp(inicio).floor("D") + pd.Timedelta(days=1), dia_f, freq="D")
    urls = [_url(d, p) for d in dias for p in NOWCAST] + [_url(dia_f, p) for p in PRONOSTICO]
    log(f"RTOFS: {len(urls)} archivos ({len(dias)} días de nowcast + pronóstico del {dia_f:%d/%m})")
    with ThreadPoolExecutor(HILOS) as ex:
        res = [r for r in ex.map(lambda u: _lee_archivo(u, idx), urls) if r is not None]
    if not res:
        raise RuntimeError("RTOFS: ningún archivo legible")
    res.sort(key=lambda r: r[0])
    t = pd.DatetimeIndex([r[0] for r in res], name="time")
    coords = {"time": t, "latitude": idx["lats"], "longitude": idx["lons"]}
    U = xr.DataArray(np.stack([r[1] for r in res]), dims=("time", "latitude", "longitude"), coords=coords)
    V = xr.DataArray(np.stack([r[2] for r in res]), dims=("time", "latitude", "longitude"), coords=coords)
    u, v, info = punto_uv(U, V, BOYA["lat"], BOYA["lon"])
    df = pd.DataFrame({"u": u, "v": v}, index=t)
    df = con_rapidez(df[~df.index.duplicated(keep="last")].dropna(how="all")).astype("float32")
    return df, dict(info, dataset="rtofs_glo_2ds_*_diag.nc (barotrópica)", corrida=f"{dia_f:%Y-%m-%d} 00z")
