# MetGeo Coronel · boya vs modelos oceanográficos globales (v1)

Dashboard Streamlit que compara **una boya real** —la Sofar Spotter + ADCP de Puerto Coronel (golfo de
Arauco), operada por la UdeC y publicada por el CDOM— con los **modelos oceánicos y de oleaje globales**
de acceso abierto. Es la versión 1 de un banco de validación que después puede crecer a más boyas
(heredando la estructura de `monitor_coast_chile_metgeo`).

```bash
.venv/bin/python ingesta.py              # boya + modelos, incremental (la primera vez ~15 min, por RTOFS)
.venv/bin/streamlit run streamlit_app.py
.venv/bin/python -m pytest -q            # 16 pruebas (las de la app se saltan si no hay data/)
```

Entorno: `.venv` con Python 3.13 (basado en el entorno conda `copernicusmarine`), dependencias en
`requirements.txt`. Copernicus Marine usa las credenciales de `~/.copernicusmarine/`.

## Qué compara

| Grupo | Modelo | Fuente | Paso | Punto usado* |
|---|---|---|---|---|
| Corriente | GLO12 Mercator (sin marea) | Copernicus `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` | 1 h | 4,0 km |
| Corriente | GLO12 total (+marea FES +Stokes) | Copernicus `..._merged-uv_PT1H-i` | 1 h | 4,0 km |
| Corriente | GLORYS12 (reanálisis) | Copernicus `cmems_mod_glo_phy_my_0.083deg_P1D-m` | 1 día | 4,0 km |
| Corriente | HYCOM ESPC-D-V02 (1/25°) | hycom.org NCSS, FMRC *best* | 3 h | 4,0 km |
| Corriente | RTOFS Global (**barotrópica**) | AWS `noaa-nws-rtofs-pds`, lectura por rangos del HDF5 | 3 h / 6 h | 4,0 km |
| Oleaje | MFWAM | Copernicus `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i` | 3 h | 9,3 km |
| Oleaje | ECMWF WAM, NOAA GFS-Wave, DWD GWAM | Open-Meteo Marine | 1 h | 9,3 km |

\* La boya está a ~1 km de la costa: ningún modelo global tiene las 4 celdas vecinas en el mar, así que se
usa la celda de mar más cercana (o la que elige Open-Meteo). Esa distancia es parte del error medido.

No incluidos en la v1: **FOAM** (Met Office; en Copernicus solo como producto regional del Atlántico NE) y
**OceanMAPS** (BoM; sin un servicio abierto práctico para series puntuales).

## La boya

| Fuente | Qué da | Desde |
|---|---|---|
| CDOM `POST https://cdom.r9.cl/get-multi-series` (series `U01sM<PARAM>000`, 30 min, UTC) | Hs, periodo medio, dirección peak, corriente (rapidez, dirección), viento | 17/07/2025 |
| API UdeC `https://puertocoronel.oceanografia.udec.cl/api` (FastAPI, `/docs`) | lo anterior + **Tp**, dirección media, dispersión | últimos 500 registros (~10 días) |

Hallazgos de los datos (verificados el 04/10/2026):

- Lo que el CDOM rotula **«Periodo Peak Oleaje» es el periodo medio** (idéntico a `meanPeriod` de la API
  UdeC). El Tp verdadero solo está en la API UdeC y se acumula desde el 24/09/2026.
- El viento del CDOM viene en **m/s**, aunque el portal lo rotule en nudos.
- El tiempo del CDOM es la lectura redondeada hacia abajo a la media hora (la de las 23:10 aparece a las
  23:00); se lleva a paso horario asignando cada lectura a la hora más cercana.
- Del 3 al 17/09/2026 el ADCP marcó ~0,5 m/s sostenidos (diez veces lo habitual): el QC lo descarta
  (mediana de 24 h > 0,30 m/s), además de rango y picos.
- **Convención de la dirección del ADCP, por confirmar**: contra los tres modelos de corriente la boya sale
  girada ~165°, y contra el viento medido queda a la *derecha* (en el hemisferio sur la deriva se espera a la
  izquierda). La app usa «hacia» y ofrece «Ajustes → Invertir la dirección» para comparar. Conviene
  confirmarlo con la UdeC (LOFEC).

## Primeros resultados (17/07/2025 – 04/10/2026, solo análisis)

- **Oleaje:** todos sobreestiman Hs en la bahía (sesgo +0,4 m MFWAM; +0,65 a +0,77 m ECMWF/GFS/GWAM) con
  r = 0,74–0,79: el punto del modelo está a 9 km, mar afuera, sin el abrigo de la bahía.
- **Corriente:** sin correlación con GLO12 / GLORYS en la convención actual (|ρ| 0,1–0,3, giro ~165°); los
  modelos dan 3–8 cm/s de corriente media y la boya < 1 cm/s.

## Publicación

- Repo público en GitHub; app en Streamlit Community Cloud (archivo principal `streamlit_app.py`, Python 3.13).
- `.github/workflows/ingesta.yml` corre `ingesta.py` todos los días a las 09:30 UTC (06:30 de Chile) y
  commitea `data/`; Streamlit se redespliega con el commit. También se lanza a mano (`workflow_dispatch`).
- Secretos del repo: `COPERNICUSMARINE_SERVICE_USERNAME` y `COPERNICUSMARINE_SERVICE_PASSWORD`.
- La API UdeC guarda solo ~10 días: la Action diaria es la que conserva Tp y la dirección media.

## Licencia

MIT, ver [LICENSE](LICENSE). Los datos de la boya son de la UdeC (LOFEC/COPAS) vía CDOM; los de los modelos,
de sus productores (Copernicus Marine, US Navy/HYCOM, NOAA, Open-Meteo con uso no comercial).

## Estructura

```
catalogo.py        boya, variables y modelos (nombre, color, fuente, salvedades)
boya.py            CDOM + API UdeC → QC → horario (data/obs_30min.parquet, data/obs.parquet)
modelos/           extrae (punto en la grilla), cmems, hycom, rtofs, openmeteo
almacen.py         Parquet en data/ (MONITOR_DATOS para otra carpeta); fusión: lo nuevo pisa
ingesta.py         CLI incremental; estado por fuente en data/_estado.json
validacion.py      emparejamiento y métricas (escalares, circulares, vectorial de Kundu, vector progresivo)
comun.py           cargas con caché, encabezado, exportación PNG/PDF
streamlit_app.py   navegación: Monitor · Validación · Fuentes y método
app_pages/
tests/
```

Cada modelo guarda la **mejor serie disponible** en el punto, con la columna `emitido` (hora de descarga):
cada ingesta vuelve a pedir desde 4 días antes del último análisis y pisa lo anterior, así el pasado queda
con análisis y el futuro con el último pronóstico. «Solo análisis» en Validación usa solo las horas que ya
eran pasado al descargarse.

## Pendientes / ideas para la v2

1. Confirmar con la UdeC la convención de dirección y la profundidad de la celda `pos1` del ADCP.
2. HYCOM ESPC: el servidor a veces responde «Stale file handle» (pasó varias horas el 04/10/2026); la
   ingesta reintenta y, si falla, conserva lo guardado. Solo guarda ~10 días: la historia se arma día a día.
3. Validación por **plazo de pronóstico** (guardar cada corrida, no solo la mejor serie).
4. La Action guarda los Parquet en `main` (un commit diario de ~2 MB): el repo crece ~0,7 GB al año. Si
   molesta, pasar los datos a una rama `datos` huérfana (un solo commit reescrito) como en Araucanía.
5. Sumar más boyas (las de `monitor_coast_chile_metgeo`) y modelos regionales cuando haya acceso.
