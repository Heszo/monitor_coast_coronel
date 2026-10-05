"""
Almacén local en Parquet (carpeta data/, o la de MONITOR_DATOS):

- obs_30min.parquet: la boya tal como llega (cada 30 min, convención de tiempo del CDOM), sin QC;
- obs.parquet: la boya horaria, con QC aplicado (lo que lee la app);
- modelos/{modelo}.parquet: la mejor serie disponible de cada modelo en el punto de la boya, con la
  columna `emitido` (hora de la descarga). Cada ingesta pisa las horas que vuelve a traer, así el
  pasado queda con el análisis más reciente y el futuro con el último pronóstico;
- modelos/{modelo}.json: cómo se extrajo el punto (método, distancia y celda del modelo).

En GitHub los datos viven en la rama `datos` (la Action la reescribe en cada corrida, sin historia) y
la app desplegada los lee por HTTP desde REMOTO; en local se usa la carpeta data/. Solo la lectura
acepta una URL como base. Como el repo es privado, la lectura remota usa el token de
MONITOR_DATOS_TOKEN (en Streamlit Cloud, un secreto de nivel raíz, que llega como variable de entorno).
"""
import io
import json
import os
from pathlib import Path

import pandas as pd
import requests

DATOS = Path(os.environ.get("MONITOR_DATOS", Path(__file__).resolve().parent / "data"))
REMOTO = os.environ.get("MONITOR_DATOS_URL",
                        "https://raw.githubusercontent.com/Heszo/monitor_coast_coronel/datos/data")
TOKEN = os.environ.get("MONITOR_DATOS_TOKEN")  # token de GitHub de solo lectura (repo privado)


def fuente():
    """Dónde lee la app: data/ si hay una ingesta local, si no la rama `datos` de GitHub."""
    return DATOS if (DATOS / "obs.parquet").exists() else REMOTO


def _es_url(base):
    return isinstance(base, str) and base.startswith("http")


def _ruta(nombre, base=None):
    return Path(base or DATOS) / nombre


def _bytes(nombre, base):
    """Contenido de un archivo local o remoto; None si no existe."""
    if _es_url(base):
        headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
        r = requests.get(f"{base}/{nombre}", headers=headers, timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    f = _ruta(nombre, base)
    return f.read_bytes() if f.exists() else None


def lee(nombre, base=None):
    b = _bytes(nombre, base)
    if b is None:
        return pd.DataFrame()
    return pd.read_parquet(io.BytesIO(b)).sort_index()


def lee_json(nombre, base=None):
    b = _bytes(nombre, base)
    return json.loads(b.decode("utf-8")) if b else {}


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
    return lee_json(f"modelos/{modelo}.json", base)


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
