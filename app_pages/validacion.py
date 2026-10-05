"""Validación: métricas de cada modelo contra la boya en un periodo a elección, dispersión obs–modelo,
sesgo mensual y (corrientes) correlación vectorial y diagrama de vector progresivo."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as C
import validacion as val
from catalogo import BOYA, GRUPOS, MODELOS, VARIABLES

VARS = {"oleaje": ["hs", "tm", "tp", "dp", "dm"], "corriente": ["rapidez", "rumbo", "u", "v"]}

obs_todo = C.obs()
if obs_todo.empty:
    st.warning("Sin datos de la boya: corre `python ingesta.py`.", icon=":material/sensors_off:")
    st.stop()

# ------------------------------------------------------------------ controles
with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    grupo = st.segmented_control("Variables", list(GRUPOS), format_func=GRUPOS.get, default="oleaje",
                                 required=True, key="grupo_val")
    var = st.selectbox("Variable", VARS[grupo], format_func=lambda v: VARIABLES[v]["nombre"], key=f"var_{grupo}",
                       width=280)
    disponibles = C.con_datos(grupo)
    modelos = st.multiselect("Modelos", disponibles, default=disponibles, key=f"modelos_val_{grupo}",
                             format_func=lambda m: MODELOS[m]["nombre"], width=520)
    inicio_obs, fin_obs = obs_todo.index.min().date(), min(obs_todo.index.max(), C.ahora()).date()
    rango = st.date_input("Periodo", value=(inicio_obs, fin_obs), min_value=inicio_obs, max_value=fin_obs,
                          key="periodo", width=240, format="DD/MM/YYYY")
with st.container(horizontal=True, gap="large"):
    analisis = st.toggle("Solo análisis", value=True, key="solo_analisis",
                         help="Descarta las horas que todavía eran pronóstico cuando se descargaron: se valida "
                              "la mejor estimación de cada modelo, no su pronóstico.")
    marea = grupo == "corriente" and st.toggle("Quitar marea (media 25 h)", key="submareal_val")

if not isinstance(rango, (tuple, list)) or len(rango) != 2:
    st.info("Elige el inicio y el fin del periodo.", icon=":material/date_range:")
    st.stop()
t0, t1 = pd.Timestamp(rango[0]), pd.Timestamp(rango[1]) + pd.Timedelta(days=1)


def prepara(df):
    if df is None or df.empty:
        return df
    d = df[(df.index >= t0 - pd.Timedelta(days=2)) & (df.index < t1 + pd.Timedelta(days=2))]
    if marea and not val.es_diario(d):
        d = val.submareal(d)
    return d[(d.index >= t0) & (d.index < t1)]


obs = prepara(obs_todo)
pares = {}
for m in modelos:
    d = C.carga_modelo(m)
    d = C.solo_analisis(d) if analisis else d[d.index <= C.ahora()]
    pares[m] = val.empareja(obs, prepara(d), list(VARS[grupo]))

# ------------------------------------------------------------------ tabla de métricas
V = VARIABLES[var]
circular = V.get("circular", False)
filas = []
for m in modelos:
    r = val.metricas(pares[m], var)
    meta = C.carga_meta(m)
    filas.append(dict(modelo=MODELOS[m]["nombre"], n=r.get("n", 0), sesgo=r.get("sesgo"), mae=r.get("mae"),
                      rmse=r.get("rmse"), r=r.get("r"), si=r.get("si"), razon_std=r.get("razon_std"),
                      distancia=meta.get("distancia_km"),
                      paso="diario" if val.es_diario(C.carga_modelo(m)) else "horario/3 h"))
tabla = pd.DataFrame(filas)
u = V["unidad"]
st.subheader(f"{V['nombre']} · {rango[0]:%d/%m/%Y} a {rango[1]:%d/%m/%Y}", anchor=False)
cols = {"modelo": st.column_config.TextColumn("Modelo", width="medium"),
        "n": st.column_config.NumberColumn("N", help="Pares obs–modelo (horas o días)"),
        "sesgo": st.column_config.NumberColumn(f"Sesgo ({u})", format="%+.3f" if not circular else "%+.1f",
                                               help="Modelo − observado (ángulos: media circular)"),
        "mae": st.column_config.NumberColumn(f"MAE ({u})", format="%.3f" if not circular else "%.1f"),
        "rmse": st.column_config.NumberColumn(f"RMSE ({u})", format="%.3f" if not circular else "%.1f"),
        "r": st.column_config.ProgressColumn("r", min_value=-1, max_value=1, format="%.2f",
                                             help="Correlación de Pearson"),
        "si": st.column_config.NumberColumn("SI", format="%.2f", help="Índice de dispersión = RMSE / media obs"),
        "razon_std": st.column_config.NumberColumn("σ mod / σ obs", format="%.2f"),
        "distancia": st.column_config.NumberColumn("Punto a (km)", format="%.1f",
                                                   help="Distancia de la boya al punto del modelo"),
        "paso": st.column_config.TextColumn("Paso")}
mostrar = [c for c in cols if not (circular and c in ("r", "si", "razon_std"))]
st.dataframe(tabla[mostrar], column_config=cols, hide_index=True)
if var in ("tp", "dm"):
    st.caption("La boya entrega Tp y dirección media solo desde el 24/09/2026 (API UdeC): N es chico por ahora.")
if var == "tm":
    st.caption("Periodo medio: la Spotter y los modelos no usan el mismo momento espectral (MFWAM = Tm02, "
               "más corto que Tm01); parte del sesgo es de definición.")

# ------------------------------------------------------------------ vectorial (corrientes)
if grupo == "corriente":
    vec = []
    for m in modelos:
        p = pares[m]
        if {"o_u", "o_v", "m_u", "m_v"} <= set(p):
            r = val.vectorial(p.o_u, p.o_v, p.m_u, p.m_v)
            vec.append(dict(modelo=MODELOS[m]["nombre"], n=r.get("n"), rho=r.get("rho"), giro=r.get("giro"),
                            rmse_vec=None if r.get("rmse_vec") is None else r["rmse_vec"] * 100,
                            media_obs=None if r.get("media_obs") is None else r["media_obs"] * 100,
                            media_mod=None if r.get("media_mod") is None else r["media_mod"] * 100,
                            rumbo_obs=r.get("rumbo_medio_obs"), rumbo_mod=r.get("rumbo_medio_mod")))
    if vec:
        st.markdown("**Correlación vectorial** (Kundu, 1976: anomalías de u + iv)")
        st.dataframe(pd.DataFrame(vec), hide_index=True, column_config={
            "modelo": st.column_config.TextColumn("Modelo", width="medium"),
            "rho": st.column_config.ProgressColumn("|ρ|", min_value=0, max_value=1, format="%.2f"),
            "giro": st.column_config.NumberColumn("Giro θ (°)", format="%+.0f",
                                                  help="Rotación media del modelo respecto de la boya; + = antihorario"),
            "rmse_vec": st.column_config.NumberColumn("RMSE vectorial (cm/s)", format="%.1f"),
            "media_obs": st.column_config.NumberColumn("Corriente media boya (cm/s)", format="%.1f"),
            "media_mod": st.column_config.NumberColumn("Corriente media modelo (cm/s)", format="%.1f"),
            "rumbo_obs": st.column_config.NumberColumn("Rumbo medio boya (°)", format="%.0f"),
            "rumbo_mod": st.column_config.NumberColumn("Rumbo medio modelo (°)", format="%.0f")})

# ------------------------------------------------------------------ dispersión
con_pares = [m for m in modelos if len(pares[m]) and f"o_{var}" in pares[m] and pares[m][[f"o_{var}", f"m_{var}"]].dropna().shape[0] >= 3]
if not con_pares:
    st.info("Ningún modelo tiene pares con la boya en este periodo para esta variable.", icon=":material/info:")
    st.stop()
escala = 100 if u == "m/s" else 1
u_g = "cm/s" if u == "m/s" else u
n_col = min(3, len(con_pares))
n_fil = int(np.ceil(len(con_pares) / n_col))
fd = make_subplots(rows=n_fil, cols=n_col, subplot_titles=[MODELOS[m]["nombre"] for m in con_pares],
                   horizontal_spacing=0.06, vertical_spacing=0.12)
todos = pd.concat([pares[m][[f"o_{var}", f"m_{var}"]] for m in con_pares]) * escala
lo, hi = (0, 360) if circular else (float(np.nanmin(todos.values)), float(np.nanmax(todos.values)))
for k, m in enumerate(con_pares):
    fi, co = k // n_col + 1, k % n_col + 1
    p = pares[m][[f"o_{var}", f"m_{var}"]].dropna() * escala
    fd.add_trace(go.Scattergl(x=p.iloc[:, 0], y=p.iloc[:, 1], mode="markers", showlegend=False,
                              marker=dict(size=4, color=MODELOS[m]["color"], opacity=0.35),
                              hovertemplate="obs %{x:.2f} · modelo %{y:.2f}<extra></extra>"), row=fi, col=co)
    fd.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=C.GRIS, dash="dash", width=1),
                            showlegend=False, hoverinfo="skip"), row=fi, col=co)
    fd.update_xaxes(range=[lo, hi], title_text=f"boya ({u_g})", row=fi, col=co)
    fd.update_yaxes(range=[lo, hi], title_text=f"modelo ({u_g})" if co == 1 else None, row=fi, col=co)
fd.update_layout(height=340 * n_fil + 40, margin=dict(l=10, r=10, t=40, b=10))
fd.update_annotations(font_size=12)
st.markdown(f"**Boya vs modelo** · {V['nombre'].lower()}")
C.grafico(fd, f"dispersion_{var}", key="dispersion")

# ------------------------------------------------------------------ sesgo mensual
mens = pd.DataFrame({MODELOS[m]["nombre"]: val.sesgo_mensual(pares[m], var) for m in con_pares})
if len(mens) > 1:
    z = mens.T * escala
    lim = float(np.nanmax(np.abs(z.values))) if np.isfinite(z.values).any() else 1
    fh = go.Figure(go.Heatmap(z=z.values, x=[f"{t:%b %Y}" for t in z.columns], y=z.index, colorscale="RdBu_r",
                              zmin=-lim, zmax=lim, colorbar=dict(title=u_g),
                              hovertemplate="%{y} · %{x}: sesgo %{z:+.2f}<extra></extra>"))
    fh.update_layout(height=60 * len(z) + 120, margin=dict(l=10, r=10, t=30, b=10))
    st.markdown("**Sesgo mensual** (modelo − boya): rojo = el modelo sobreestima")
    C.grafico(fh, f"sesgo_mensual_{var}", key="sesgo_mensual")

# ------------------------------------------------------------------ vector progresivo
if grupo == "corriente":
    fv = go.Figure()
    for m in con_pares:
        p = pares[m]
        if {"m_u", "m_v"} <= set(p):
            dv = val.vector_progresivo(p.m_u, p.m_v)
            fv.add_trace(go.Scatter(x=dv.x, y=dv.y, mode="lines", name=MODELOS[m]["nombre"],
                                    line=dict(color=MODELOS[m]["color"], width=1.6)))
    ref = pares[con_pares[0]]
    dv = val.vector_progresivo(ref.o_u, ref.o_v)
    fv.add_trace(go.Scatter(x=dv.x, y=dv.y, mode="lines", name="Boya", line=dict(color=C.NEGRO, width=2.4)))
    fv.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(color=C.ROJO, size=9), name="inicio"))
    fv.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="este (km)",
                     yaxis_title="norte (km)", legend=dict(orientation="h", y=-0.12))
    fv.update_yaxes(scaleanchor="x", scaleratio=1)
    st.markdown("**Diagrama de vector progresivo**: desplazamiento de una partícula que siguiera la corriente "
                "medida en el punto (solo en las horas comunes con cada modelo; la boya, en las horas comunes "
                f"con {MODELOS[con_pares[0]]['nombre']}).")
    C.grafico(fv, "vector_progresivo", key="vector_progresivo")

st.caption(f"{BOYA['nombre']}: promedios horarios con QC. Los modelos se comparan en su paso nativo, solo en "
           "las horas (o días) que ambos tienen. GLORYS: medias diarias contra la media diaria de la boya.")
