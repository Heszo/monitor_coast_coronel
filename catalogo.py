"""
Catálogo del monitor: la boya, las variables y los modelos oceanográficos globales que se comparan.

Convenciones (todas las series se guardan así):
- tiempo en UTC, sin zona, paso horario (GLORYS: diario);
- oleaje: dirección DE DONDE VIENE (convención meteorológica), en grados desde el norte;
- corriente: componentes u (este) y v (norte) en m/s; la dirección es HACIA DONDE VA (oceanográfica).
"""
BOYA = dict(
    id="coronel", nombre="Boya Puerto Coronel", lat=-37.03488, lon=-73.15510,
    descripcion="Sofar Spotter (oleaje) con ADCP Aanderaa (corriente) frente al muelle de Puerto Coronel, "
                "golfo de Arauco. Opera UdeC (LOFEC/COPAS) y la publica el CDOM.",
    inicio="2025-07-17",
)

# grupo → variables; "circular" = ángulo (métricas y promedios por componentes)
VARIABLES = {
    "hs": dict(nombre="Altura significativa", unidad="m", dec=2, grupo="oleaje"),
    "tp": dict(nombre="Periodo peak", unidad="s", dec=1, grupo="oleaje"),
    "tm": dict(nombre="Periodo medio", unidad="s", dec=1, grupo="oleaje"),
    "dp": dict(nombre="Dirección peak (desde)", unidad="°", dec=0, grupo="oleaje", circular=True),
    "dm": dict(nombre="Dirección media (desde)", unidad="°", dec=0, grupo="oleaje", circular=True),
    "u": dict(nombre="Corriente u (este)", unidad="m/s", dec=3, grupo="corriente"),
    "v": dict(nombre="Corriente v (norte)", unidad="m/s", dec=3, grupo="corriente"),
    "rapidez": dict(nombre="Rapidez de la corriente", unidad="m/s", dec=3, grupo="corriente"),
    "rumbo": dict(nombre="Dirección de la corriente (hacia)", unidad="°", dec=0, grupo="corriente", circular=True),
    "viento": dict(nombre="Viento medio", unidad="m/s", dec=1, grupo="viento"),
    "viento_dir": dict(nombre="Dirección del viento (desde)", unidad="°", dec=0, grupo="viento", circular=True),
    "rafaga": dict(nombre="Ráfaga", unidad="m/s", dec=1, grupo="viento"),
}
GRUPOS = {"oleaje": "Oleaje", "corriente": "Corrientes"}

# tipo: "pronostico" (análisis + pronóstico, se renueva a diario), "reanalisis" (sin tiempo real)
MODELOS = {
    # --------------------------------------------------------------- corrientes
    "glo12": dict(nombre="GLO12 Mercator", grupo="corriente", color="#1f77b4", tipo="pronostico",
                  fuente="Copernicus Marine · GLOBAL_ANALYSISFORECAST_PHY_001_024 (horario, 0,49 m)",
                  detalle="NEMO + asimilación SAM2, 1/12°, 50 niveles. Corriente euleriana SIN marea."),
    "glo12_total": dict(nombre="GLO12 total (+marea +Stokes)", grupo="corriente", color="#17becf", tipo="pronostico",
                        fuente="Copernicus Marine · merged-uv (utotal, vtotal)",
                        detalle="La misma GLO12 más la corriente de marea (FES) y la deriva de Stokes de MFWAM: "
                                "lo más parecido a lo que mide un ADCP cerca de la superficie."),
    "espc": dict(nombre="HYCOM ESPC-D-V02", grupo="corriente", color="#d62728", tipo="pronostico",
                 fuente="hycom.org · FMRC_ESPC-D-V02_uv3z (best), NCSS",
                 detalle="US Navy (NRL/FNMOC), HYCOM 1/25°, 3-horario, 0 m. El servidor solo guarda la "
                         "colección de corridas reciente (~10 días): la historia se acumula en cada ingesta."),
    "rtofs": dict(nombre="RTOFS Global (barotrópica)", grupo="corriente", color="#ff7f0e", tipo="pronostico",
                  fuente="NOAA NCEP · noaa-nws-rtofs-pds (AWS), rtofs_glo_2ds_*_diag.nc",
                  detalle="HYCOM 1/12°. En acceso abierto solo publica la velocidad BAROTRÓPICA (promedio en la "
                          "columna), no la de superficie: sirve de referencia, no es comparable 1 a 1."),
    "glorys": dict(nombre="GLORYS12 (reanálisis)", grupo="corriente", color="#9467bd", tipo="reanalisis",
                   fuente="Copernicus Marine · GLOBAL_MULTIYEAR_PHY_001_030 (diario, 0,49 m)",
                   detalle="Reanálisis NEMO 1/12°. Medias diarias; se publica con ~3-4 meses de atraso."),
    # --------------------------------------------------------------- oleaje
    "mfwam": dict(nombre="MFWAM (Météo-France)", grupo="oleaje", color="#1f77b4", tipo="pronostico",
                  fuente="Copernicus Marine · GLOBAL_ANALYSISFORECAST_WAV_001_027 (3-horario)",
                  detalle="1/12°, con asimilación de altimetría. Dirección peak = VPED."),
    "ecmwf_wam": dict(nombre="ECMWF WAM", grupo="oleaje", color="#2ca02c", tipo="pronostico",
                      fuente="Open-Meteo Marine · ecmwf_wam025", detalle="0,25°, acoplado al IFS."),
    "gfswave": dict(nombre="NOAA GFS-Wave", grupo="oleaje", color="#d62728", tipo="pronostico",
                    fuente="Open-Meteo Marine · ncep_gfswave025", detalle="WAVEWATCH III, 0,25°."),
    "gwam": dict(nombre="DWD GWAM", grupo="oleaje", color="#ff7f0e", tipo="pronostico",
                 fuente="Open-Meteo Marine · dwd_gwam", detalle="WAM del servicio alemán, 0,25°."),
}
