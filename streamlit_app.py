"""
MetGeo Coronel: la boya de Puerto Coronel contra los modelos oceanográficos globales (v1).

    streamlit run streamlit_app.py
"""
import streamlit as st

import comun as C

st.set_page_config(page_title="MetGeo Coronel · boya vs modelos oceánicos", page_icon=str(C.LOGO_SOLO),
                   layout="wide")
st.logo(str(C.LOGO_COMPLETO), icon_image=str(C.LOGO_SOLO), size="large")

pagina = st.navigation([
    st.Page("app_pages/monitor.py", title="Monitor", icon=":material/radar:", default=True),
    st.Page("app_pages/validacion.py", title="Validación", icon=":material/fact_check:"),
    st.Page("app_pages/fuentes.py", title="Fuentes y método", icon=":material/info:"),
], position="top")

with st.container(horizontal=True, vertical_alignment="center"):
    st.title("Monitor Coronel" if pagina.title == "Monitor" else pagina.title, icon=pagina.icon, anchor=False)
    C.ajustes()
C.metricas_ahora()
st.space("small")

pagina.run()

st.space("large")
st.caption("MetGeo · Boya Puerto Coronel (UdeC / CDOM) vs modelos globales · Bruno Herrera · [Instagram](" + C.INSTAGRAM +
           ") · [LinkedIn](" + C.LINKEDIN + ") · uso no comercial", text_alignment="center")
