"""
Lo que comparten las páginas: cargas con caché, conversión de hora, métricas "ahora" y utilidades de
gráficos (línea gráfica heredada de MetGeo Araucanía / Costa Chile).

La app solo lee: data/ si hay una ingesta local, si no la rama `datos` de GitHub (almacen.fuente()).
"""
import base64
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import almacen
from catalogo import BOYA, MODELOS, VARIABLES
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LOGO_COMPLETO = RAIZ / "static" / "logo_completo.png"
LOGO_SOLO = RAIZ / "static" / "logo_solo.png"
NEGRO, ROJO, GRIS = "#111111", "#B5323C", "#8c8c8c"
EJE_T = dict(tickformat="%d/%m<br>%H:%M", nticks=8, tickangle=0)
ZONA_CL = "America/Santiago"
INSTAGRAM = "https://www.instagram.com/metgeo.spa/"
LINKEDIN = "https://www.linkedin.com/company/metgeo-spa/"
PIE = ("MetGeo · Boya Puerto Coronel (UdeC/CDOM) vs modelos globales: Copernicus Marine, HYCOM, "
       "NOAA RTOFS, Open-Meteo")
_RASTER = {
    "satelite": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                 "Esri World Imagery"),
    "calles": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "© colaboradores de OpenStreetMap"),
}
BASES = {k: dict(nombre=n, credito=_RASTER[k][1], estilo="data:application/json," + json.dumps(dict(
    version=8, sources={"base": dict(type="raster", tiles=[_RASTER[k][0]], tileSize=256, attribution=_RASTER[k][1])},
    layers=[dict(id="base", type="raster", source="base")]), separators=(",", ":")))
    for k, n in (("satelite", "Satélite"), ("calles", "Calles"))}


# ------------------------------------------------------------------ cargas con caché
FUENTE = almacen.fuente()


@st.cache_data(ttl="10m", show_spinner="Leyendo la boya…")
def carga_obs():
    return almacen.lee("obs.parquet", FUENTE)


@st.cache_data(ttl="30m", show_spinner="Leyendo los modelos…")
def carga_modelo(modelo):
    return almacen.lee_modelo(modelo, FUENTE)


@st.cache_data(ttl="30m", show_spinner=False)
def carga_meta(modelo):
    return almacen.lee_meta(modelo, FUENTE)


@st.cache_data(ttl="10m", show_spinner=False)
def carga_estado():
    return almacen.lee_json("_estado.json", FUENTE)


def modelos_de(grupo):
    return [m for m, d in MODELOS.items() if d["grupo"] == grupo]


def con_datos(grupo):
    return [m for m in modelos_de(grupo) if not carga_modelo(m).empty]


def solo_analisis(df):
    """Solo las horas que ya eran pasado cuando se descargaron (análisis), sin pronósticos."""
    if df.empty or "emitido" not in df:
        return df
    return df[df.index <= pd.to_datetime(df["emitido"]).values]


# ------------------------------------------------------------------ hora y formato
def ahora():
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


def hora_local():
    return st.session_state.get("hora_local", False)


def a_pantalla(idx, local=None):
    """Índice UTC → hora de Chile (sin zona, para Plotly) si se pidió."""
    local = hora_local() if local is None else local
    if not local:
        return idx
    return pd.DatetimeIndex(idx).tz_localize("UTC").tz_convert(ZONA_CL).tz_localize(None)


def rotulo_hora():
    return "hora de Chile" if hora_local() else "UTC"


def fmt(v, dec, unidad=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{(' ' + unidad) if unidad else ''}"


def cardinal(grados):
    if grados is None or np.isnan(grados):
        return ""
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"][
        int(round(grados / 22.5)) % 16]


# ------------------------------------------------------------------ encabezado
def ajustes():
    with st.popover("Ajustes", icon=":material/tune:"):
        st.toggle("Hora de Chile (si no, UTC)", value=False, key="hora_local")
        st.toggle("Invertir la dirección de la corriente de la boya", value=False, key="invertir_adcp",
                  help="Trata la dirección del ADCP como «desde» en vez de «hacia». Contra los tres modelos la "
                       "corriente de la boya sale girada ~165°, y contra el viento queda a la derecha (en el "
                       "hemisferio sur se espera a la izquierda): la convención está por confirmar con la UdeC.")


def obs():
    """La boya horaria, con la dirección de la corriente invertida si se pidió en «Ajustes»."""
    df = carga_obs()
    if st.session_state.get("invertir_adcp") and {"u", "v", "rumbo"} <= set(df):
        df = df.copy()
        df[["u", "v"]] = -df[["u", "v"]]
        df["rumbo"] = (df["rumbo"] + 180) % 360
    return df


def metricas_ahora():
    """Última lectura de la boya (horaria, con QC)."""
    obs_ = obs()
    if obs_.empty:
        st.warning("Todavía no hay datos de la boya: corre `python ingesta.py`.", icon=":material/sensors_off:")
        return
    rec = obs_[obs_.index >= obs_.index.max() - pd.Timedelta(hours=12)]

    def ultimo(v):
        s = rec[v].dropna() if v in rec else pd.Series(dtype=float)
        return (float(s.iloc[-1]), s.index[-1]) if len(s) else (np.nan, None)

    tarjetas, horas = [], []
    for v, icono, extra in [("hs", "tsunami", None), ("tp", "timer", None), ("tm", "av_timer", None),
                            ("dp", "explore", "desde"), ("rapidez", "water", None), ("rumbo", "navigation", "hacia"),
                            ("viento", "air", None)]:
        val, t = ultimo(v)
        if t is not None:
            horas.append(t)
        V = VARIABLES[v]
        texto = fmt(val, V["dec"], V["unidad"])
        if v == "rapidez" and not np.isnan(val):
            texto = fmt(val * 100, 1, "cm/s")
        delta = f"{extra} el {cardinal(val)}" if extra and not np.isnan(val) else None
        tarjetas.append((V["nombre"].split(" (")[0], texto, delta, icono))
    if horas:
        h = a_pantalla(pd.DatetimeIndex([max(horas)]))[0]
        edad = ahora() - max(horas)
        atraso = f" · :red[atrasada {edad.total_seconds() / 3600:.0f} h]" if edad > pd.Timedelta(hours=3) else ""
        st.caption(f"Ahora en la **{BOYA['nombre']}** · última hora con dato {h:%d/%m %H:%M} {rotulo_hora()}"
                   f"{atraso}. Promedios horarios con control de calidad.")
    with st.container(horizontal=True, gap="small"):
        for nombre, valor, delta, icono in tarjetas:
            st.metric(nombre, valor, delta, delta_color="off", delta_arrow="off", border=True,
                      icon=f":material/{icono}:")


# ------------------------------------------------------------------ gráficos
def barra(boton="resetScale2d"):
    return {"displayModeBar": True, "displaylogo": False, "modeBarButtons": [[boton]]}


def _logo_uri():
    """El logo de MetGeo como data URI (Plotly lo incrusta en la imagen y en el PDF)."""
    return "data:image/png;base64," + base64.b64encode(LOGO_COMPLETO.read_bytes()).decode()


ENCABEZADO = 52   # px extra arriba del gráfico exportado para el logo y la fuente
LOGO_ALTO = 36    # px; el ancho sale de la proporción del archivo (746×180)


def exporta(fig, formato, ancho=1400):
    """El gráfico como PNG (doble resolución) o PDF, con fondo blanco, el logo de MetGeo arriba a la
    izquierda y la fuente arriba a la derecha (Kaleido con Chrome; en Streamlit Cloud, el de packages.txt)."""
    f = go.Figure(fig)
    m = f.layout.margin
    alto = (f.layout.height or 500) + ENCABEZADO
    t = (m.t or 0) + ENCABEZADO
    graf_ancho = max(ancho - (m.l or 0) - (m.r or 0), 1)
    graf_alto = max(alto - t - (m.b or 0), 1)
    f.update_layout(template="plotly_white", paper_bgcolor="white", margin=dict(t=t))
    # el logo y la fuente van arriba de todo: sobre el borde superior del área del gráfico, sumando el margen
    f.add_layout_image(source=_logo_uri(), xref="paper", yref="paper", x=0, y=1 + (t - 8) / graf_alto,
                       xanchor="left", yanchor="top", sizing="contain", layer="above",
                       sizex=LOGO_ALTO * 746 / 180 / graf_ancho, sizey=LOGO_ALTO / graf_alto)
    f.add_annotation(text=PIE, xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="bottom",
                     yshift=t - 8 - 16, showarrow=False, font=dict(size=10, color="#777"))
    return f.to_image(format=formato, width=ancho, height=alto, scale=2 if formato == "png" else 1)


def grafico(fig, nombre, key=None):
    """st.plotly_chart y botones PNG/PDF (la imagen se genera recién al hacer clic)."""
    st.plotly_chart(fig, config=barra(), key=key)
    base = f"metgeo_coronel_{nombre}_{pd.Timestamp.now():%Y%m%d_%H%M}"
    with st.container(horizontal=True, gap="small", horizontal_alignment="right"):
        for formato, mime in (("png", "image/png"), ("pdf", "application/pdf")):
            st.download_button(formato.upper(), lambda formato=formato: exporta(fig, formato),
                               file_name=f"{base}.{formato}", mime=mime, type="tertiary",
                               icon=":material/download:", on_click="ignore", key=f"baja_{key or nombre}_{formato}",
                               help=f"Guardar este gráfico en {formato.upper()}")


def linea_ahora(fig, x, fila=None):
    """add_shape en vez de add_vline (falla con Timestamps de pandas)."""
    eje = "" if fila in (None, 1) else fila
    xs = pd.Timestamp(x).isoformat()
    fig.add_shape(type="line", x0=xs, x1=xs, y0=0, y1=1, xref=f"x{eje}", yref=f"y{eje} domain",
                  line=dict(color=ROJO, width=1.4, dash="dot"))


def eje_circular(fig, **kw):
    fig.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360], ticktext=["N", "E", "S", "O", "N"], **kw)
