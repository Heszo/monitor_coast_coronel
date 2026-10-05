"""
Observaciones de la boya de Puerto Coronel desde dos fuentes públicas de la misma boya:

1. CDOM (cdom.r9.cl, POST /get-multi-series): historia completa desde jul-2025, cada 30 min.
   Serie = "U01" + resolución + "M" + parámetro + "000" (resolución "s" = 30 min).
   OJO: lo que el portal rotula "Periodo Peak Oleaje" (WAPE) es el periodo MEDIO de la Spotter
   (idéntico a meanPeriod de la API UdeC); el periodo peak solo está en la API UdeC.
   El tiempo (epoch ms, UTC) es la lectura redondeada hacia abajo a la media hora: la lectura UdeC
   de las 23:10 aparece a las 23:00. Unidades base: m, s, °, cm/s, m/s (el viento NO viene en
   nudos aunque el portal lo rotule así; verificado contra la API UdeC el 04/10/2026).
2. API UdeC (puertocoronel.oceanografia.udec.cl/api): últimos 500 registros (~10 días); suma la
   dirección media del oleaje. Se lleva a la misma convención de tiempo que el CDOM.

Luego: QC (rango + picos en la corriente) y paso horario. La hora H promedia las dos lecturas
cuyo tiempo real cae en [H-30 min, H+30 min); ángulos y corriente se promedian por componentes.
"""
import numpy as np
import pandas as pd
import requests

import almacen
from catalogo import BOYA

UA = {"User-Agent": "Mozilla/5.0 (monitor-coronel MetGeo; divulgacion no comercial)"}
URL_CDOM = "https://cdom.r9.cl/get-multi-series"
REF_CDOM = "https://cdom.r9.cl/generator/UDEC/view/ocean/lOt2JS84FZJNw8rnkXk9tnViU"
URL_UDEC = "https://puertocoronel.oceanografia.udec.cl/api"

# parámetro CDOM → (variable, factor a unidades del catálogo)
CDOM = {"WAHE": ("hs", 1.0), "WAPE": ("tm", 1.0), "SPD0": ("dp", 1.0), "COMD": ("rapidez", 0.01),
        "CODR": ("rumbo", 1.0), "WSPD": ("viento", 1.0), "WDIR": ("viento_dir", 1.0), "SWSP": ("rafaga", 1.0)}
UDEC_OLAS = {"sofarptcrn_significantWaveHeight": "hs", "sofarptcrn_peakPeriod": "tp", "sofarptcrn_meanPeriod": "tm",
             "sofarptcrn_peakDirection": "dp", "sofarptcrn_meanDirection": "dm"}
UDEC_CORR = {"sofarptcrn_adcp_pos1_speed_ms": "rapidez", "sofarptcrn_adcp_pos1_direction_deg": "rumbo"}
TRAMO = pd.Timedelta(days=45)  # días por consulta al CDOM

# límites físicos plausibles en una bahía semiprotegida
RANGOS = {"hs": (0.02, 12), "tp": (1.5, 25), "tm": (1.5, 20), "dp": (0, 360), "dm": (0, 360), "rapidez": (0, 1.0),
          "rumbo": (0, 360), "viento": (0, 40), "viento_dir": (0, 360), "rafaga": (0, 60)}
NIVEL_CORRIENTE = 0.30  # m/s, mediana de 24 h
ANGULOS = {"dp", "dm", "rumbo", "viento_dir"}


# ------------------------------------------------------------------ descarga
def cdom(parametro, inicio, fin, http=None):
    """Serie de un parámetro del CDOM entre inicio y fin (UTC), en tramos de TRAMO."""
    http = http or requests
    clave, partes = f"U01sM{parametro}000", []
    t = pd.Timestamp(inicio)
    while t < pd.Timestamp(fin):
        t1 = min(t + TRAMO, pd.Timestamp(fin))
        r = http.post(URL_CDOM, json={"series": [f"x0={clave}"], "start": int(t.tz_localize("UTC").timestamp()),
                                      "end": int(t1.tz_localize("UTC").timestamp()), "domain": "UDEC",
                                      "resolution": "s"},
                      headers=UA | {"X-Requested-With": "XMLHttpRequest", "Referer": REF_CDOM}, timeout=120)
        r.raise_for_status()
        d = pd.DataFrame(r.json()["series"].get(clave, []))
        if len(d):
            partes.append(pd.Series(d["y"].astype(float).values, index=pd.to_datetime(d["x"], unit="ms")))
        t = t1
    if not partes:
        return pd.Series(dtype=float)
    s = pd.concat(partes).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def descarga_cdom(inicio, fin, http=None):
    cols = {}
    for par, (var, f) in CDOM.items():
        s = cdom(par, inicio, fin, http)
        if len(s):
            cols[var] = s * f
    return pd.DataFrame(cols)


def _lecturas(sensores, mapa):
    cols = {}
    for s_code, var in mapa.items():
        lect = sensores.get(s_code, {}).get("lecturas", [])
        if lect:
            t = pd.to_datetime([x["tiempo_lectura"] for x in lect]).floor("30min")
            cols[var] = pd.Series([x["dato"] for x in lect], index=t, dtype=float).groupby(level=0).last()
    return pd.DataFrame(cols)


def descarga_udec(http=None):
    """Últimos ~10 días de oleaje y corriente, en la convención de tiempo del CDOM."""
    http = http or requests
    partes = []
    for ruta, mapa in (("oleaje", UDEC_OLAS), ("corriente", UDEC_CORR)):
        r = http.get(f"{URL_UDEC}/{ruta}/ultimos", params={"limit": 500}, headers=UA, timeout=90)
        r.raise_for_status()
        partes.append(_lecturas(r.json().get("sensores", {}), mapa))
    return pd.concat(partes, axis=1).sort_index()


def posicion(http=None):
    try:
        return (http or requests).get(f"{URL_UDEC}/posicion", headers=UA, timeout=30).json()
    except Exception:  # noqa: BLE001
        return {}


# ------------------------------------------------------------------ QC y paso horario
def qc(df):
    """Anula lo que cae fuera de rango, los picos de la corriente (desvío de la mediana móvil de
    7 lecturas mayor que 0,15 m/s y que 6 MAD) y los tramos con nivel anómalo persistente (mediana
    de 24 h sobre NIVEL_CORRIENTE: en sep-2026 el ADCP marcó ~0,5 m/s durante dos semanas, diez veces
    lo normal en la bahía). Devuelve (df limpio, {variable: n anulados})."""
    df = df.copy()
    anulados = {}
    for v, (lo, hi) in RANGOS.items():
        if v in df:
            malo = df[v].notna() & ~df[v].between(lo, hi)
            df.loc[malo, v] = np.nan
            anulados[v] = int(malo.sum())
    if "rapidez" in df:
        s = df["rapidez"]
        med = s.rolling(7, center=True, min_periods=3).median()
        mad = (s - med).abs().rolling(7, center=True, min_periods=3).median()
        pico = (s - med).abs() > np.maximum(0.15, 6 * mad)
        nivel = s.rolling("24h", center=True, min_periods=6).median() > NIVEL_CORRIENTE
        pico |= nivel & s.notna()
        df.loc[pico, ["rapidez", "rumbo"]] = np.nan
        anulados["rapidez"] = anulados.get("rapidez", 0) + int(pico.sum())
    if {"rapidez", "rumbo"} <= set(df):
        sin_par = df["rapidez"].isna() | df["rumbo"].isna()
        df.loc[sin_par, ["rapidez", "rumbo"]] = np.nan
    return df, anulados


def uv(rapidez, rumbo):
    """Rapidez y dirección HACIA donde va → componentes (u este, v norte)."""
    r = np.deg2rad(rumbo)
    return rapidez * np.sin(r), rapidez * np.cos(r)


def rumbo_de(u, v):
    return np.rad2deg(np.arctan2(u, v)) % 360


def media_circular(s):
    r = np.deg2rad(s.dropna())
    if r.empty:
        return np.nan
    return float(np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


def a_horario(df):
    """30 min (convención CDOM) → horario. La lectura de las xx:00 (real xx:10) y la de las xx:30
    (real xx:40) se asignan a la hora más cercana: xx:00 y xx+1:00."""
    if df.empty:
        return df
    hora = (df.index + pd.Timedelta(minutes=30)).floor("h")
    g = df.groupby(hora)
    out = pd.DataFrame(index=g.size().index)
    for v in df.columns:
        if v in ANGULOS:
            if v == "rumbo":
                continue
            out[v] = g[v].agg(media_circular)
        elif v != "rapidez":
            out[v] = g[v].mean()
    if {"rapidez", "rumbo"} <= set(df):
        u, v = uv(df["rapidez"], df["rumbo"])
        uu, vv = u.groupby(hora).mean(), v.groupby(hora).mean()
        out["u"], out["v"] = uu, vv
        out["rapidez"], out["rumbo"] = np.hypot(uu, vv), rumbo_de(uu, vv)
    out.index.name = "time"
    return out.dropna(how="all").astype("float32")


# ------------------------------------------------------------------ ingesta
def ingesta(desde=None, http=None, base=None, log=print):
    """Trae lo nuevo (desde la última lectura guardada menos 1 día, o `desde`), lo une a lo guardado y
    rehace la serie horaria. Devuelve un resumen."""
    crudo = almacen.lee("obs_30min.parquet", base)
    ahora = pd.Timestamp.now(tz="UTC").tz_localize(None)
    if desde is None:
        desde = (crudo.index.max() - pd.Timedelta(days=1)) if len(crudo) else pd.Timestamp(BOYA["inicio"])
    nuevo = descarga_cdom(desde, ahora + pd.Timedelta(hours=1), http)
    log(f"CDOM: {len(nuevo)} lecturas desde {pd.Timestamp(desde):%Y-%m-%d}")
    try:
        u = descarga_udec(http)
        log(f"UdeC: {len(u)} lecturas ({u.index.min():%d/%m %H:%M} a {u.index.max():%d/%m %H:%M})")
        nuevo = u.combine_first(nuevo) if len(nuevo) else u  # UdeC agrega dm; en lo común, mismas cifras
    except Exception as ex:  # noqa: BLE001  (la historia del CDOM basta)
        log(f"UdeC no disponible: {ex}")
    crudo = almacen.guarda(nuevo, "obs_30min.parquet", base) if len(nuevo) else crudo
    limpio, anulados = qc(crudo)
    horario = a_horario(limpio)
    almacen.guarda(horario, "obs.parquet", base, fusionar=False)
    return dict(lecturas=len(crudo), horas=len(horario), anulados_qc=anulados,
                ultimo=str(crudo.index.max()) if len(crudo) else None, posicion=posicion(http))
