"""Conectores de modelos: cada uno devuelve (tabla indexada por time con las variables del catálogo, meta)."""
import numpy as np


def con_rapidez(df):
    """Agrega rapidez y rumbo (hacia donde va) a partir de u y v."""
    if {"u", "v"} <= set(df):
        df["rapidez"] = np.hypot(df["u"], df["v"])
        df["rumbo"] = np.rad2deg(np.arctan2(df["u"], df["v"])) % 360
    return df
