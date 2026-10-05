"""Fuentes y método: la boya, cada modelo con el estado de su última descarga, y las salvedades."""
import pandas as pd
import streamlit as st

import comun as C
from catalogo import BOYA, GRUPOS, MODELOS

estado = C.carga_estado()
eb = estado.get("boya", {})

st.subheader("La boya", anchor=False)
st.markdown(f"""
**{BOYA['nombre']}** ({BOYA['lat']:.4f}°, {BOYA['lon']:.4f}°). {BOYA['descripcion']}

- **Historia** (desde jul-2025, cada 30 min): portal [CDOM](https://cdom.r9.cl/cdom/sistema-de-informacion-portuaria-puerto-coronel),
  servicio `get-multi-series`.
- **Tiempo real** (últimos ~10 días, más variables): [API de la UdeC](https://puertocoronel.oceanografia.udec.cl/).
- Última ingesta: {eb.get('actualizado', '—')[:16]} UTC · {eb.get('lecturas', '—')} lecturas de 30 min,
  {eb.get('horas', '—')} horas. QC anuló: {", ".join(f"{k} {v}" for k, v in eb.get('anulados_qc', {}).items() if v) or "nada"}.
""")

st.subheader("Modelos", anchor=False)
filas = []
for m, d in MODELOS.items():
    e = estado.get("modelos", {}).get(m, {})
    meta = C.carga_meta(m)
    guardado = C.carga_modelo(m)
    filas.append(dict(
        grupo=GRUPOS[d["grupo"]], modelo=d["nombre"], tipo="reanálisis" if d["tipo"] == "reanalisis" else "análisis + pronóstico",
        estado="✅" if e.get("ok") else ("⚠️ " + e.get("error", "sin descargar")[:90] if e else "sin descargar"),
        desde=guardado.index.min() if len(guardado) else None, hasta=guardado.index.max() if len(guardado) else None,
        punto=f"{meta.get('metodo', '—')} · {meta.get('distancia_km', '—')} km" if meta else "—",
        fuente=d["fuente"], detalle=d["detalle"]))
st.dataframe(pd.DataFrame(filas), hide_index=True, column_config={
    "desde": st.column_config.DatetimeColumn("Desde", format="DD/MM/YYYY"),
    "hasta": st.column_config.DatetimeColumn("Hasta", format="DD/MM/YYYY HH:mm"),
    "detalle": st.column_config.TextColumn("Detalle", width="large"),
    "fuente": st.column_config.TextColumn("Fuente", width="medium")})

st.subheader("Método y salvedades", anchor=False)
st.markdown("""
- **Punto del modelo.** Se interpola en la boya (bilineal) si las 4 celdas que la rodean son de mar; si no, se usa la
  celda de mar más cercana (hasta 20 km; oleaje de MFWAM 30 km). La boya está a ~1 km de la costa, dentro del golfo de
  Arauco: todos los modelos globales caen en el segundo caso y comparan un punto **4 a 9 km mar afuera**, más expuesto
  al oleaje y a la corriente que la bahía. Ese error de representatividad es parte de lo que la validación mide.
- **Periodo.** Lo que el CDOM rotula «Periodo Peak Oleaje» es el **periodo medio** de la Spotter (idéntico a
  `meanPeriod` de la API UdeC): el monitor lo trata como periodo medio. El periodo peak verdadero solo está en la API
  UdeC, desde el 24/09/2026, y se acumula desde entonces.
- **Corriente de la boya.** Celda más superficial del ADCP (`pos1`), dirección hacia donde va. QC: rango 0–1 m/s, picos
  (desvío de la mediana móvil > 0,15 m/s y 6 MAD) y tramos con mediana de 24 h > 0,30 m/s: del 3 al 17/09/2026 el
  ADCP marcó ~0,5 m/s (diez veces lo habitual) y se descarta.
- **Convención de la dirección del ADCP, por confirmar.** Contra GLO12, GLO12 total y GLORYS la corriente de la boya
  sale girada ~165° (correlación vectorial |ρ| 0,1–0,3), y contra el viento medido en la misma boya queda ~100° a la
  *derecha* del viento, cuando en el hemisferio sur la deriva superficial se espera a la *izquierda*. Ambas pistas
  apuntan a que el ADCP informe «desde» y no «hacia». La app usa «hacia» por defecto; «Ajustes → Invertir la
  dirección» permite comparar con la otra convención mientras se confirma con la UdeC (LOFEC).
- **Marea.** GLO12, ESPC, RTOFS y GLORYS no simulan marea; el ADCP sí la mide. «GLO12 total» suma la marea (FES) y la
  deriva de Stokes. El interruptor «Quitar marea» aplica una media móvil de 25 h a todos por igual.
- **RTOFS** en acceso abierto solo publica la velocidad **barotrópica** (promedio en la columna): es una referencia,
  no una comparación 1 a 1 con la corriente superficial.
- **HYCOM ESPC**: el servidor solo mantiene la colección de corridas reciente (~1 semana atrás + 16 días); la historia
  se arma acumulando cada ingesta.
- **GLORYS12** se publica con ~3-4 meses de atraso: hoy cubre hasta junio de 2026.
- **Análisis vs pronóstico.** Cada hora de un modelo guarda cuándo se descargó (`emitido`); «Solo análisis» valida la
  mejor estimación de cada modelo. La validación por plazo de pronóstico queda para una versión siguiente.
- **No incluidos en la v1:** FOAM (Met Office; en Copernicus solo como producto regional del Atlántico NE) y OceanMAPS
  (BoM; sin un servicio abierto práctico para series puntuales).
""")
