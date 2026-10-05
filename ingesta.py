"""
Ingesta incremental: boya (CDOM + API UdeC) y modelos en el punto de la boya.

    python ingesta.py                       # todo, incremental
    python ingesta.py --solo-obs            # solo la boya (rápido, ~10 s)
    python ingesta.py --modelos glo12,mfwam # algunos modelos
    python ingesta.py --desde 2025-07-17    # rehace desde esa fecha (primera carga)

La primera vez cada modelo parte en el inicio de la boya (RTOFS: 14 días, ESPC: lo que tenga el
servidor). Después se vuelve a pedir desde REPASO días antes del último análisis guardado, para
reemplazar pronósticos vencidos por análisis. Una fuente que falla no detiene a las demás: el error
queda en data/_estado.json y la app lo muestra.
"""
import argparse
import json
import time
import traceback

import pandas as pd

import almacen
import boya
from catalogo import BOYA, MODELOS
from modelos import cmems, hycom, openmeteo, rtofs

REPASO = pd.Timedelta(days=4)
RTOFS_INICIAL = pd.Timedelta(days=14)


def _ahora():
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


def desde_para(modelo, guardado, forzado=None):
    if forzado is not None:
        return pd.Timestamp(forzado)
    inicio = pd.Timestamp(BOYA["inicio"])
    if modelo == "rtofs" and guardado.empty:
        return _ahora().floor("D") - RTOFS_INICIAL
    if guardado.empty:
        return inicio
    if modelo == "glorys":
        return guardado.index.max() - pd.Timedelta(days=2)
    # último dato que ya era pasado cuando se descargó (análisis), menos el repaso
    emit = pd.to_datetime(guardado["emitido"]).values if "emitido" in guardado else guardado.index
    analisis = guardado.index[guardado.index <= emit]
    ref = analisis.max() if len(analisis) else guardado.index.min()
    return max(inicio, min(ref, _ahora()) - REPASO)


def lee_modelo(modelo, desde, log):
    fin = _ahora() + pd.Timedelta(days=11)
    if modelo in cmems.DATASETS:
        if modelo == "glorys":
            fin = _ahora()
        return cmems.lee(modelo, desde, fin)
    if modelo in openmeteo.MODELOS:
        return openmeteo.lee(modelo, desde)
    if modelo == "espc":
        return hycom.lee()
    if modelo == "rtofs":
        return rtofs.lee(desde, log=log)
    raise KeyError(modelo)


def ingesta_modelos(modelos, desde=None, log=print):
    estado = {}
    for m in modelos:
        t0 = time.time()
        guardado = almacen.lee_modelo(m)
        d = desde_para(m, guardado, desde)
        log(f"· {MODELOS[m]['nombre']}: desde {d:%Y-%m-%d %H:%M}")
        try:
            df, meta = lee_modelo(m, d, log)
            if df.empty:
                raise RuntimeError("la fuente no devolvió datos en el punto de la boya")
            df["emitido"] = _ahora().floor("min")
            todo = almacen.guarda_modelo(m, df, meta | {"actualizado": str(_ahora())})
            estado[m] = dict(ok=True, filas_nuevas=len(df), filas=len(todo), desde=str(todo.index.min()),
                             hasta=str(todo.index.max()), segundos=round(time.time() - t0, 1), **meta)
            log(f"  {len(df)} filas ({df.index.min():%d/%m/%Y} a {df.index.max():%d/%m/%Y %H:%M}), "
                f"{meta.get('metodo')} a {meta.get('distancia_km')} km, {time.time() - t0:.0f} s")
        except Exception as ex:  # noqa: BLE001
            estado[m] = dict(ok=False, error=f"{type(ex).__name__}: {str(ex)[:300]}", segundos=round(time.time() - t0, 1))
            log(f"  ERROR {estado[m]['error']}")
            log(traceback.format_exc(limit=2))
        guarda_estado({"modelos": {m: estado[m]}})  # tras cada modelo: un corte no borra lo hecho
    return estado


def guarda_estado(parte):
    f = almacen.DATOS / "_estado.json"
    estado = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for k, v in parte.items():
        if k == "modelos":
            estado[k] = (estado.get(k) or {}) | v  # un modelo reemplaza su entrada, no las de los demás
        else:
            estado[k] = v
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(estado, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo-obs", action="store_true")
    ap.add_argument("--solo-modelos", action="store_true")
    ap.add_argument("--modelos", help=f"lista separada por comas (de {', '.join(MODELOS)})")
    ap.add_argument("--desde", help="AAAA-MM-DD: rehace desde esa fecha")
    a = ap.parse_args()
    if not a.solo_modelos:
        print("Boya Puerto Coronel")
        r = boya.ingesta(desde=a.desde)
        guarda_estado({"boya": r | {"actualizado": str(_ahora())}})
        print(f"  {r['horas']} horas; QC anuló {r['anulados_qc']}")
    if not a.solo_obs:
        modelos = a.modelos.split(",") if a.modelos else list(MODELOS)
        print("Modelos")
        ingesta_modelos(modelos, a.desde)


if __name__ == "__main__":
    main()
