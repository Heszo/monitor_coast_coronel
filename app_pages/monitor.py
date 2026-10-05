"""Monitor: la boya contra cada modelo en una ventana móvil (pasado reciente + pronóstico), con el mapa
de la boya y de las celdas que usó cada modelo."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from plotly.subplots import make_subplots

import comun as C
import validacion as val
from catalogo import BOYA, GRUPOS, MODELOS, VARIABLES

PANELES = {
    "oleaje": [("hs", ["hs"]), ("tm", ["tm"]), ("tp", ["tp"]), ("dp", ["dp", "dm"])],
    "corriente": [("rapidez", ["rapidez"]), ("rumbo", ["rumbo"]), ("u", ["u"]), ("v", ["v"])],
}

# ------------------------------------------------------------------ controles
with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    grupo = st.segmented_control("Variables", list(GRUPOS), format_func=GRUPOS.get, default="oleaje",
                                 required=True, key="grupo", bind="query-params")
    disponibles = C.con_datos(grupo)
    modelos = st.multiselect("Modelos", disponibles, default=disponibles, key=f"modelos_{grupo}",
                             format_func=lambda m: MODELOS[m]["nombre"], width=520,
                             placeholder="sin modelos descargados")
    pasado = st.slider("Días hacia atrás", 1, 60, 10, key="pasado", width=220)
    futuro = st.slider("Días de pronóstico", 0, 10, 5, key="futuro", width=220)
    marea = grupo == "corriente" and st.toggle("Quitar marea (media 25 h)", key="submareal",
                                               help="Media móvil centrada de 25 h sobre u y v, en la boya y en "
                                                    "los modelos: deja la corriente submareal. GLO12, ESPC y "
                                                    "GLORYS no simulan marea; GLO12 total sí.")

ahora = C.ahora()
t0, t1 = ahora.floor("h") - pd.Timedelta(days=pasado), ahora.floor("h") + pd.Timedelta(days=futuro)


def ventana(df):
    if df is None or df.empty:
        return df
    pad = pd.Timedelta(hours=13) if marea else pd.Timedelta(0)  # el filtro necesita los bordes
    d = df[(df.index >= t0 - pad) & (df.index <= t1 + pad)]
    if marea and not val.es_diario(d):  # GLORYS es diario: ya no tiene marea
        d = val.submareal(d)
    return d[(d.index >= t0) & (d.index <= t1)]


obs = ventana(C.obs())
mods = {m: ventana(C.carga_modelo(m)) for m in modelos}

# ------------------------------------------------------------------ mapa
col_mapa, col_serie = st.columns([2, 5], gap="medium")
with col_mapa:
    base = st.segmented_control("Mapa base", list(C.BASES), default="satelite", required=True, key="mapa_base",
                                format_func=lambda k: C.BASES[k]["nombre"])
    filas = [dict(nombre=BOYA["nombre"], detalle="observación", lat=BOYA["lat"], lon=BOYA["lon"],
                  color=[181, 50, 60, 255], radio=9)]
    for m in modelos:
        meta = C.carga_meta(m)
        if meta.get("celda"):
            h = MODELOS[m]["color"].lstrip("#")
            filas.append(dict(nombre=MODELOS[m]["nombre"], lat=meta["celda"][0], lon=meta["celda"][1],
                              detalle=f"{meta.get('metodo')} · {meta.get('distancia_km')} km de la boya",
                              color=[int(h[i:i + 2], 16) for i in (0, 2, 4)] + [230], radio=7))
    puntos = pd.DataFrame(filas)
    lineas = pd.DataFrame([dict(desde=[BOYA["lon"], BOYA["lat"]], hasta=[f["lon"], f["lat"]], color=f["color"])
                           for f in filas[1:]])
    deck = pdk.Deck(
        layers=[*([pdk.Layer("LineLayer", data=lineas, get_source_position="desde", get_target_position="hasta",
                             get_color="color", get_width=2)] if len(lineas) else []),
                pdk.Layer("ScatterplotLayer", data=puntos, pickable=True, get_position=["lon", "lat"],
                          get_fill_color="color", get_radius="radio", radius_units="'pixels'", stroked=True,
                          get_line_color=[255, 255, 255, 230], line_width_min_pixels=1)],
        map_style=C.BASES[base]["estilo"], map_provider="carto",
        initial_view_state=pdk.ViewState(latitude=BOYA["lat"] + 0.01, longitude=BOYA["lon"] - 0.04, zoom=10.3),
        tooltip={"html": "<b>{nombre}</b><br/>{detalle}", "style": {"fontSize": "12px"}})
    st.pydeck_chart(deck, height=520)
    st.caption(f"Rojo: la boya. Cada color: el punto de grilla que usa ese modelo (interpolado o la celda de mar "
               f"más cercana: la boya está a ~1 km de la costa). Mapa base: {C.BASES[base]['credito']}.")

# ------------------------------------------------------------------ series
paneles = PANELES[grupo]
x = C.a_pantalla
fig = make_subplots(rows=len(paneles), cols=1, shared_xaxes=True, vertical_spacing=0.05,
                    subplot_titles=[f"{VARIABLES[p]['nombre']} ({'cm/s' if VARIABLES[p]['unidad'] == 'm/s' else VARIABLES[p]['unidad']})"
                                    for p, _ in paneles])
for i, (titulo, vs) in enumerate(paneles, start=1):
    escala = 100 if VARIABLES[titulo]["unidad"] == "m/s" else 1
    circular = VARIABLES[titulo].get("circular", False)
    for m in modelos:
        d = mods[m]
        for v in vs:
            if d is None or v not in d or d[v].isna().all():
                continue
            s = d[v].dropna()
            fig.add_trace(go.Scatter(
                x=x(s.index), y=s * escala, mode="markers" if circular else "lines",
                name=MODELOS[m]["nombre"], legendgroup=m, showlegend=m not in {t.legendgroup for t in fig.data},
                line=dict(color=MODELOS[m]["color"], width=1.4, dash="dot" if v == "dm" and titulo == "dp" else None),
                marker=dict(size=4, color=MODELOS[m]["color"], symbol="circle-open" if v == "dm" else "circle"),
                hovertemplate=f"{MODELOS[m]['nombre']} · {v}: %{{y:.{VARIABLES[v]['dec']}f}}<extra></extra>"),
                row=i, col=1)
    for v in vs:
        if obs is None or v not in obs or obs[v].isna().all():
            continue
        s = obs[v].dropna()
        fig.add_trace(go.Scatter(
            x=x(s.index), y=s * escala, mode="markers" if circular else "lines",
            name="Boya (observado)", legendgroup="obs", showlegend="obs" not in {t.legendgroup for t in fig.data},
            line=dict(color=C.NEGRO, width=2.2), marker=dict(size=4 if v == "dp" else 5, color=C.NEGRO,
                                                             symbol="circle-open" if v == "dm" else "circle"),
            hovertemplate=f"Boya · {v}: %{{y:.{VARIABLES[v]['dec']}f}}<extra></extra>"), row=i, col=1)
    if circular:
        C.eje_circular(fig, row=i, col=1)
    C.linea_ahora(fig, x(pd.DatetimeIndex([ahora]))[0], fila=i)
fig.update_layout(height=200 * len(paneles) + 80, hovermode="x unified", margin=dict(l=10, r=10, t=40, b=10),
                  legend=dict(orientation="h", y=-0.06, yanchor="top"))
fig.update_xaxes(**C.EJE_T)
fig.update_annotations(font_size=12, x=0, xanchor="left")
with col_serie:
    C.grafico(fig, f"monitor_{grupo}")
    notas = [f"Línea roja punteada: ahora. Horas en {C.rotulo_hora()}."]
    if grupo == "oleaje":
        notas.append("El periodo peak (Tp) y la dirección media de la boya solo existen desde el 24/09/2026 (API "
                     "UdeC); antes el CDOM publica el periodo medio. Dirección: puntos llenos = peak, vacíos = media. "
                     "El periodo medio de los modelos no es exactamente el mismo momento espectral que el de la "
                     "Spotter (MFWAM: Tm02; Open-Meteo: periodo medio del modelo).")
    else:
        notas.append("Corriente de la boya: celda más superficial del ADCP. RTOFS es la velocidad barotrópica "
                     "(promedio en la columna). Dirección = hacia donde va.")
    for n in notas:
        st.caption(n)
    errores = {m: e for m, e in C.carga_estado().get("modelos", {}).items()
               if not e.get("ok") and MODELOS.get(m, {}).get("grupo") == grupo}
    for m, e in errores.items():
        st.warning(f"{MODELOS[m]['nombre']}: la última descarga falló ({e.get('error', '')[:160]}). "
                   "Se muestra lo guardado antes.", icon=":material/cloud_off:")
