"""
Emparejamiento observación–modelo y métricas.

- Escalares (hs, tp, tm, rapidez, u, v): N, sesgo (modelo − obs), MAE, RMSE, r de Pearson, índice de
  dispersión SI = RMSE / media obs, y razón de desviaciones estándar.
- Ángulos (dp, dm, rumbo): diferencias llevadas a [−180°, 180°); sesgo = media circular de la
  diferencia, MAE y RMSE de la diferencia.
- Vector corriente: correlación compleja de Kundu (1976) sobre las anomalías, ρ = ⟨w_o* w_m⟩ /
  √(⟨|w_o|²⟩⟨|w_m|²⟩) con w = u + iv; |ρ| ∈ [0, 1] y el ángulo θ = arg ρ es el giro medio del
  modelo respecto de la observación (positivo = antihorario). RMSE vectorial = √⟨|w_m − w_o|²⟩.

El emparejamiento usa solo las horas que ambos tienen (sin interpolar el modelo). Para modelos
diarios (GLORYS) la observación se lleva a medias diarias (por componentes; mínimo 18 h por día).
"""
import numpy as np
import pandas as pd

from catalogo import VARIABLES

MIN_HORAS_DIA = 18
FILTRO_MAREA = "25h"


def es_circular(var):
    return VARIABLES[var].get("circular", False)


def diario(obs):
    """Medias diarias: escalares con media, ángulos por componentes, corriente desde u y v."""
    n = obs.resample("1D").count()
    out = obs.resample("1D").mean(numeric_only=True)
    for v in obs.columns:
        if es_circular(v) and v != "rumbo":
            r = np.deg2rad(obs[v])
            out[v] = np.rad2deg(np.arctan2(np.sin(r).resample("1D").mean(), np.cos(r).resample("1D").mean())) % 360
    if {"u", "v"} <= set(out):
        out["rapidez"] = np.hypot(out["u"], out["v"])
        out["rumbo"] = np.rad2deg(np.arctan2(out["u"], out["v"])) % 360
    return out.where(n >= MIN_HORAS_DIA)


def submareal(df):
    """Media móvil centrada de 25 h sobre u y v (quita la marea semidiurna y diurna de forma aproximada)."""
    if not {"u", "v"} <= set(df) or df.empty:
        return df
    out = df.copy()
    for c in ("u", "v"):
        out[c] = df[c].rolling(FILTRO_MAREA, center=True, min_periods=6).mean()
    out["rapidez"] = np.hypot(out["u"], out["v"])
    out["rumbo"] = np.rad2deg(np.arctan2(out["u"], out["v"])) % 360
    return out


def es_diario(df):
    if len(df) < 3:
        return False
    return pd.Series(df.index).diff().median() >= pd.Timedelta(hours=23)


def empareja(obs, mod, cols):
    """Tabla con columnas o_<var> y m_<var> en las horas comunes con dato en ambas."""
    if mod is None or mod.empty or obs is None or obs.empty:
        return pd.DataFrame()
    if es_diario(mod):
        obs = diario(obs)
    cols = [c for c in dict.fromkeys(cols) if c in obs and c in mod]  # sin repetidas
    o = obs[cols].add_prefix("o_")
    m = mod[cols].add_prefix("m_")
    return o.join(m, how="inner")


def escalar(o, m):
    d = pd.concat([o, m], axis=1).dropna()
    if len(d) < 3:
        return dict(n=len(d))
    o, m = d.iloc[:, 0].astype(float), d.iloc[:, 1].astype(float)
    e = m - o
    rmse = float(np.sqrt((e ** 2).mean()))
    return dict(n=len(d), sesgo=float(e.mean()), mae=float(e.abs().mean()), rmse=rmse,
                r=float(np.corrcoef(o, m)[0, 1]) if o.std() > 0 and m.std() > 0 else np.nan,
                si=rmse / float(o.mean()) if o.mean() else np.nan,
                razon_std=float(m.std() / o.std()) if o.std() > 0 else np.nan)


def dif_angular(o, m):
    return ((m - o + 180) % 360) - 180


def circular(o, m):
    d = pd.concat([o, m], axis=1).dropna()
    if len(d) < 3:
        return dict(n=len(d))
    e = dif_angular(d.iloc[:, 0].astype(float), d.iloc[:, 1].astype(float))
    r = np.deg2rad(e)
    return dict(n=len(d), sesgo=float(np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean()))),
                mae=float(e.abs().mean()), rmse=float(np.sqrt((e ** 2).mean())))


def vectorial(uo, vo, um, vm):
    d = pd.concat([uo, vo, um, vm], axis=1).dropna()
    if len(d) < 3:
        return dict(n=len(d))
    wo = d.iloc[:, 0].values + 1j * d.iloc[:, 1].values
    wm = d.iloc[:, 2].values + 1j * d.iloc[:, 3].values
    rmse = float(np.sqrt(np.mean(np.abs(wm - wo) ** 2)))
    ao, am = wo - wo.mean(), wm - wm.mean()
    rho = np.mean(np.conj(ao) * am) / np.sqrt(np.mean(np.abs(ao) ** 2) * np.mean(np.abs(am) ** 2))
    return dict(n=len(d), rho=float(np.abs(rho)), giro=float(np.degrees(np.angle(rho))), rmse_vec=rmse,
                media_obs=float(np.abs(wo.mean())), media_mod=float(np.abs(wm.mean())),
                rumbo_medio_obs=float(np.degrees(np.arctan2(wo.mean().real, wo.mean().imag)) % 360),
                rumbo_medio_mod=float(np.degrees(np.arctan2(wm.mean().real, wm.mean().imag)) % 360))


def metricas(par, var):
    o, m = par.get(f"o_{var}"), par.get(f"m_{var}")
    if o is None or m is None:
        return dict(n=0)
    return circular(o, m) if es_circular(var) else escalar(o, m)


def sesgo_mensual(par, var):
    """Sesgo por mes (para el mapa de calor). Ángulos: media circular de la diferencia."""
    o, m = par.get(f"o_{var}"), par.get(f"m_{var}")
    if o is None or m is None:
        return pd.Series(dtype=float)
    e = dif_angular(o, m) if es_circular(var) else (m - o)
    return e.dropna().resample("MS").mean()


def vector_progresivo(u, v):
    """Desplazamiento acumulado (km) de una partícula que sigue la corriente medida en un punto
    (diagrama de vector progresivo). Huecos: no suman."""
    u, v = u.dropna(), v.dropna()
    idx = u.index.intersection(v.index)
    if len(idx) < 2:
        return pd.DataFrame(columns=["x", "y"])
    dt = pd.Series(idx, index=idx).diff().dt.total_seconds().clip(upper=3 * 3600).fillna(0)
    return pd.DataFrame({"x": (u[idx] * dt).cumsum() / 1000, "y": (v[idx] * dt).cumsum() / 1000})
