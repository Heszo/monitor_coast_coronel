"""Pruebas sin red: boya (QC, paso horario), extracción puntual, almacén, métricas e ingesta incremental."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

import almacen
import boya
import ingesta
import validacion as val
from modelos.extrae import punto, punto_uv


# ------------------------------------------------------------------ boya
def test_horario_asigna_lecturas_a_la_hora_mas_cercana():
    # convención CDOM: 10:00 (real 10:10) y 10:30 (real 10:40) → 10:00 y 11:00
    t = pd.to_datetime(["2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01 10:30"])
    df = pd.DataFrame({"hs": [1.0, 2.0, 4.0]}, index=t)
    h = boya.a_horario(df)
    assert h.loc["2026-01-01 10:00", "hs"] == pytest.approx(1.5)
    assert h.loc["2026-01-01 11:00", "hs"] == pytest.approx(4.0)


def test_horario_promedia_angulos_y_corriente_por_componentes():
    t = pd.to_datetime(["2026-01-01 09:30", "2026-01-01 10:00"])
    df = pd.DataFrame({"dp": [350.0, 10.0], "rapidez": [0.1, 0.1], "rumbo": [90.0, 270.0]}, index=t)
    h = boya.a_horario(df).iloc[0]
    assert min(h.dp, 360 - h.dp) < 1e-3          # media de 350° y 10° es 0°, no 180°
    assert h.rapidez == pytest.approx(0, abs=1e-6)  # este y oeste se anulan
    u, v = boya.uv(np.array([1.0]), np.array([90.0]))
    assert u[0] == pytest.approx(1) and v[0] == pytest.approx(0, abs=1e-12)


def test_qc_rango_picos_y_nivel_persistente():
    t = pd.date_range("2026-09-01", periods=200, freq="30min")
    r = np.full(200, 0.04)
    r[10] = 0.9                       # pico aislado
    r[100:200] = 0.5                  # nivel anómalo persistente (> 24 h)
    df = pd.DataFrame({"rapidez": r, "rumbo": 90.0, "hs": 0.5}, index=t)
    df.iloc[5, df.columns.get_loc("hs")] = 40  # fuera de rango
    limpio, anulados = boya.qc(df)
    assert np.isnan(limpio.hs.iloc[5]) and anulados["hs"] == 1
    assert np.isnan(limpio.rapidez.iloc[10]) and np.isnan(limpio.rumbo.iloc[10])
    assert limpio.rapidez.iloc[150:].isna().all()
    assert limpio.rapidez.iloc[20:80].notna().all()


# ------------------------------------------------------------------ extracción
def _ventana(valores, lats, lons, n=4):
    data = np.broadcast_to(valores, (n, *valores.shape)).copy()
    return xr.DataArray(data, dims=("time", "latitude", "longitude"),
                        coords={"time": pd.date_range("2026-01-01", periods=n, freq="h"), "latitude": lats,
                                "longitude": lons})


def test_punto_bilineal_y_vecino_de_mar():
    lats, lons = np.array([-37.1, -37.0]), np.array([-73.2, -73.1])
    w = _ventana(np.array([[1.0, 2.0], [3.0, 4.0]]), lats, lons)
    v, info = punto(w, -37.05, -73.15)
    assert info["metodo"] == "bilineal" and v[0] == pytest.approx(2.5)
    w2 = _ventana(np.array([[1.0, np.nan], [3.0, 4.0]]), lats, lons)
    v2, info2 = punto(w2, -37.08, -73.12)
    assert info2["metodo"] == "vecino_mar" and v2[0] in (1.0, 4.0)
    v3, info3 = punto(_ventana(np.full((2, 2), np.nan), lats, lons), -37.05, -73.15)
    assert info3["metodo"] == "sin_mar" and np.isnan(v3).all()


def test_punto_uv_usa_la_misma_celda():
    lats, lons = np.array([-37.1, -37.0]), np.array([-73.2, -73.1])
    u = _ventana(np.array([[1.0, np.nan], [3.0, 4.0]]), lats, lons)
    v = _ventana(np.array([[5.0, 6.0], [np.nan, 8.0]]), lats, lons)  # máscara distinta
    vu, vv, info = punto_uv(u, v, -37.02, -73.18)
    assert info["metodo"] == "vecino_mar" and (vu[0], vv[0]) in ((1.0, 5.0), (4.0, 8.0))


# ------------------------------------------------------------------ almacén e ingesta
def test_fusiona_prefiere_lo_nuevo(tmp_path):
    t = pd.date_range("2026-01-01", periods=3, freq="h")
    almacen.guarda(pd.DataFrame({"hs": [1.0, 1.0, 1.0]}, index=t), "x.parquet", tmp_path)
    nuevas = pd.to_datetime(["2026-01-01 02:00", "2026-01-01 03:00"])
    df = almacen.guarda(pd.DataFrame({"hs": [2.0, 2.0]}, index=nuevas), "x.parquet", tmp_path)
    assert df.hs.tolist() == [1.0, 1.0, 2.0, 2.0]  # 02:00 se pisa, 03:00 se agrega


def test_desde_para_repasa_el_ultimo_analisis():
    t = pd.date_range("2026-01-01", periods=10 * 24, freq="h")
    g = pd.DataFrame({"u": 0.0, "emitido": pd.Timestamp("2026-01-05")}, index=t)
    d = ingesta.desde_para("glo12", g)
    assert d == pd.Timestamp("2026-01-05") - ingesta.REPASO
    assert ingesta.desde_para("glo12", pd.DataFrame()) == pd.Timestamp("2025-07-17")


# ------------------------------------------------------------------ métricas
def test_metricas_escalares():
    o = pd.Series([1.0, 2.0, 3.0, 4.0])
    m = o + 0.5
    r = val.escalar(o, m)
    assert r["sesgo"] == pytest.approx(0.5) and r["rmse"] == pytest.approx(0.5) and r["r"] == pytest.approx(1)


def test_metricas_circulares_cruzan_el_norte():
    r = val.circular(pd.Series([355.0, 5.0, 10.0]), pd.Series([5.0, 15.0, 20.0]))
    assert r["sesgo"] == pytest.approx(10) and r["mae"] == pytest.approx(10)


def test_correlacion_vectorial_detecta_giro():
    rng = np.random.default_rng(0)
    w = rng.normal(size=500) + 1j * rng.normal(size=500)
    wm = w * np.exp(1j * np.deg2rad(30))  # el modelo gira 30° antihorario
    r = val.vectorial(pd.Series(w.real), pd.Series(w.imag), pd.Series(wm.real), pd.Series(wm.imag))
    assert r["rho"] == pytest.approx(1) and r["giro"] == pytest.approx(30)


def test_empareja_modelo_diario_con_media_diaria():
    t = pd.date_range("2026-01-01", periods=72, freq="h")
    obs = pd.DataFrame({"u": 0.1, "v": 0.0, "rapidez": 0.1, "rumbo": 90.0}, index=t)
    mod = pd.DataFrame({"u": [0.2, 0.2, 0.2], "v": 0.0}, index=pd.date_range("2026-01-01", periods=3, freq="D"))
    p = val.empareja(obs, mod, ["u", "v"])
    assert len(p) == 3 and p.o_u.iloc[0] == pytest.approx(0.1)
