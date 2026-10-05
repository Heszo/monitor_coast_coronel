"""Humo de la app: cada página corre sin excepciones con los datos de data/ (se salta si no hay ingesta)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import almacen

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

pytestmark = pytest.mark.skipif(not (almacen.DATOS / "obs.parquet").exists(), reason="sin ingesta en data/")


@pytest.mark.parametrize("pagina", ["app_pages/monitor.py", "app_pages/validacion.py", "app_pages/fuentes.py"])
def test_pagina_sin_excepciones(pagina):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    if pagina != "app_pages/monitor.py":
        at.switch_page(pagina).run()
    assert not at.exception, [e.value for e in at.exception]


def test_monitor_corrientes_con_filtro_de_marea():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.segmented_control(key="grupo").set_value("corriente").run()
    at.toggle(key="submareal").set_value(True).run()
    assert not at.exception, [e.value for e in at.exception]


def test_validacion_corrientes():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page("app_pages/validacion.py").run()
    at.segmented_control(key="grupo_val").set_value("corriente").run()
    at.toggle(key="submareal_val").set_value(True).run()
    assert not at.exception, [e.value for e in at.exception]
