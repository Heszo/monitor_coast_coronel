"""
Copernicus Marine en el punto de la boya: GLO12 (con y sin marea), MFWAM y GLORYS12.

Se abre el dataset perezoso en una caja de ±0,25° (servicio arco-time-series, pensado para series
largas en pocos puntos), se carga la ventana entera y se extrae el punto (modelos.extrae). Se guarda
el paso nativo (1 h, 3 h o 1 día): la comparación se hace solo en las horas que ambos tienen.
Credenciales: `copernicusmarine login` o COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD.
"""
import numpy as np
import pandas as pd

from catalogo import BOYA
from modelos import con_rapidez
from modelos.extrae import punto, punto_uv

CAJA = 0.25
DATASETS = {
    # superficie = primer nivel (0,49 m)
    "glo12": dict(dataset="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m", uv=("uo", "vo"), superficie=True),
    "glo12_total": dict(dataset="cmems_mod_glo_phy_anfc_merged-uv_PT1H-i", uv=("utotal", "vtotal"), superficie=True),
    "glorys": dict(dataset="cmems_mod_glo_phy_my_0.083deg_P1D-m", uv=("uo", "vo"), superficie=True),
    # la máscara del oleaje es más gruesa en la costa: radio mayor
    "mfwam": dict(dataset="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i", radio_km=30.0,
                  vars={"VHM0": "hs", "VTPK": "tp", "VTM02": "tm", "VPED": "dp", "VMDR": "dm"}),
}
CIRCULARES = {"dp", "dm"}


def abre(dataset, variables, inicio, fin, superficie=False):
    import copernicusmarine as cm
    args = dict(dataset_id=dataset, variables=list(variables), start_datetime=f"{inicio:%Y-%m-%dT%H:%M:%S}",
                end_datetime=f"{fin:%Y-%m-%dT%H:%M:%S}",
                minimum_latitude=BOYA["lat"] - CAJA, maximum_latitude=BOYA["lat"] + CAJA,
                minimum_longitude=BOYA["lon"] - CAJA, maximum_longitude=BOYA["lon"] + CAJA)
    if superficie:
        args |= dict(minimum_depth=0, maximum_depth=1)
    try:
        return cm.open_dataset(service="arco-time-series", **args)
    except Exception:  # noqa: BLE001  (el dataset no ofrece ese servicio)
        return cm.open_dataset(**args)


def _circular(win, lat, lon, radio):
    """Ángulo por componentes: se interpolan seno y coseno."""
    r = np.deg2rad(win)
    s, info = punto(np.sin(r), lat, lon, radio)
    c, _ = punto(np.cos(r), lat, lon, radio)
    return np.rad2deg(np.arctan2(s, c)) % 360, info


def lee(modelo, inicio, fin):
    spec = DATASETS[modelo]
    variables = spec.get("uv") or list(spec["vars"])
    ds = abre(spec["dataset"], variables, inicio, fin, spec.get("superficie", False)).load()
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    radio = spec.get("radio_km", 20.0)
    lat, lon = BOYA["lat"], BOYA["lon"]
    t = pd.DatetimeIndex(ds.time.values, name="time")
    if "uv" in spec:
        u, v, info = punto_uv(ds[spec["uv"][0]], ds[spec["uv"][1]], lat, lon, radio)
        df = pd.DataFrame({"u": u, "v": v}, index=t)
        df = con_rapidez(df)
    else:
        cols, info = {}, None
        for fuente, var in spec["vars"].items():
            if fuente not in ds:
                continue
            f = _circular if var in CIRCULARES else punto
            vals, i = f(ds[fuente], lat, lon, radio)
            cols[var], info = vals, info or i
        df = pd.DataFrame(cols, index=t)
    df = df.dropna(how="all").astype("float32")
    return df, dict(info, dataset=spec["dataset"])
