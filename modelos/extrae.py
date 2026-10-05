"""
Serie de un modelo en el punto de la boya, a partir de una ventana (time, latitude, longitude) que
lo rodea (heredado de monitor_coast_chile_metgeo):

- bilineal (xarray.interp) si las 4 celdas que rodean el punto son de mar;
- si no, la celda de mar más cercana dentro de `radio_km` (la boya está a ~1 km de la costa, dentro
  del golfo de Arauco: en grillas de 1/12° casi siempre cae en este caso);
- si tampoco hay, NaN. Se informa el método, la distancia y la celda usada.
"""
import numpy as np

RADIO_KM = 20.0


def distancia_km(lat1, lon1, lat2, lon2):
    f1, f2 = np.deg2rad(lat1), np.deg2rad(lat2)
    a = np.sin((f2 - f1) / 2) ** 2 + np.cos(f1) * np.cos(f2) * np.sin(np.deg2rad(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _bilineal(win, lat, lon):
    i, j = np.searchsorted(win.latitude.values, lat) - 1, np.searchsorted(win.longitude.values, lon) - 1
    return win.isel(latitude=slice(i, i + 2), longitude=slice(j, j + 2)).interp(latitude=lat, longitude=lon).values


def mascara(win):
    """Celdas de mar: las que tienen algún dato en el tiempo."""
    return np.isfinite(win.values).any(axis=0)


def punto(win, lat, lon, radio_km=RADIO_KM, valido=None):
    """(valores, info). `win`: DataArray (time, latitude, longitude) con coordenadas crecientes.
    `valido`: máscara de mar a usar (para que u y v salgan de la misma celda)."""
    lats, lons = win.latitude.values, win.longitude.values
    valido = mascara(win) if valido is None else valido
    i, j = np.searchsorted(lats, lat) - 1, np.searchsorted(lons, lon) - 1
    if 0 <= i < len(lats) - 1 and 0 <= j < len(lons) - 1 and valido[i:i + 2, j:j + 2].all():
        return _bilineal(win, lat, lon), dict(metodo="bilineal", distancia_km=0.0, celda=[float(lat), float(lon)])
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    d = np.where(valido, distancia_km(lat, lon, la, lo), np.inf)
    k = np.unravel_index(d.argmin(), d.shape)
    if d[k] <= radio_km:
        return win.values[:, k[0], k[1]], dict(metodo="vecino_mar", distancia_km=round(float(d[k]), 1),
                                               celda=[round(float(lats[k[0]]), 4), round(float(lons[k[1]]), 4)])
    return np.full(win.sizes["time"], np.nan), dict(metodo="sin_mar", distancia_km=None, celda=None)


def punto_uv(u, v, lat, lon, radio_km=RADIO_KM):
    """u y v en la misma celda (o la misma interpolación)."""
    valido = mascara(u) & mascara(v)
    vu, info = punto(u, lat, lon, radio_km, valido)
    vv, _ = punto(v, lat, lon, radio_km, valido)
    return vu, vv, info
