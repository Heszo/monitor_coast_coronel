"""
Almacén local en Parquet (carpeta data/, o la de MONITOR_DATOS):

- obs_30min.parquet: la boya tal como llega (cada 30 min, convención de tiempo del CDOM), sin QC;
- obs.parquet: la boya horaria, con QC aplicado (lo que lee la app);
- modelos/{modelo}.parquet: la mejor serie disponible de cada modelo en el punto de la boya, con la
  columna `emitido` (hora de la descarga). Cada ingesta pisa las horas que vuelve a traer, así el
  pasado queda con el análisis más reciente y el futuro con el último pronóstico;
- modelos/{modelo}.json: cómo se extrajo el punto (método, distancia y celda del modelo).
"""
import json
import os
from pathlib import Path

import pandas as pd

DATOS = Path(os.environ.get("MONITOR_DATOS", Path(__file__).resolve().parent / "data"))


def _ruta(nombre, base=None):
    return Path(base or DATOS) / nombre


def lee(nombre, base=None):
    f = _ruta(nombre, base)
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_parquet(f)
    return df.sort_index()


def fusiona(viejo, nuevo):
    """Une dos tablas indexadas por tiempo; en las horas repetidas gana la nueva (fila completa)."""
    if viejo is None or viejo.empty:
        return nuevo.sort_index()
    if nuevo is None or nuevo.empty:
        return viejo.sort_index()
    df = pd.concat([viejo, nuevo])
    return df[~df.index.duplicated(keep="last")].sort_index()


def guarda(df, nombre, base=None, fusionar=True):
    f = _ruta(nombre, base)
    f.parent.mkdir(parents=True, exist_ok=True)
    if fusionar:
        df = fusiona(lee(nombre, base), df)
    df.index.name = "time"
    df.to_parquet(f)
    return df


def lee_meta(modelo, base=None):
    f = _ruta(f"modelos/{modelo}.json", base)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def guarda_meta(modelo, meta, base=None):
    f = _ruta(f"modelos/{modelo}.json", base)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def lee_modelo(modelo, base=None):
    return lee(f"modelos/{modelo}.parquet", base)


def guarda_modelo(modelo, df, meta=None, base=None):
    if meta:
        guarda_meta(modelo, meta, base)
    return guarda(df, f"modelos/{modelo}.parquet", base)
