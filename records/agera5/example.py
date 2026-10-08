"""Read AgERA5 daily values for a few points from the ECMWF ARCO Zarr store.

Needs a free Copernicus CDS account and its Personal Access Token (see AGENTS.md):
  pip install xarray zarr dask fsspec aiohttp
  CDSAPI_KEY=<token> python example.py
"""

import os
from pathlib import Path

import xarray as xr

# "geoChunked" = small spatial tiles, long time runs: cheap for long time series at a few places.
# Swap in .../cadl-arco-time-001/.../timeChunked.zarr (one day per chunk) for maps on a few days.
URL = "https://arco.datastores.ecmwf.int/cadl-arco-geo-001/arco/sis_agrometeorological_indicators/all/geoChunked.zarr"


def cds_key() -> str:
    """CDSAPI_KEY env var, else the `key:` line of ~/.cdsapirc."""
    if key := os.environ.get("CDSAPI_KEY"):
        return key
    rc = Path.home() / ".cdsapirc"
    if rc.exists():
        for line in rc.read_text().splitlines():
            if line.startswith("key:"):
                return line.split(":", 1)[1].strip()
    raise SystemExit("No CDS key: set CDSAPI_KEY or create ~/.cdsapirc")


ds = xr.open_zarr(
    URL,
    consolidated=True,
    chunks={},
    storage_options={"headers": {"Authorization": f"Bearer {cds_key()}"}},
)

# Pick variables and dates first, then all points in one vectorised sel.
variables = ["Temperature_Air_2m_Max_24h", "Temperature_Air_2m_Min_24h", "Precipitation_Flux"]
lats = [-1.29, 9.03]  # Nairobi, Addis Ababa
lons = [36.82, 38.74]
points = dict(latitude=xr.DataArray(lats, dims="pt"), longitude=xr.DataArray(lons, dims="pt"))

sub = ds[variables].sel(time=slice("2023-01-01", "2023-12-31")).sel(**points, method="nearest").compute()

df = sub.to_dataframe().reset_index()
df["tmax_c"] = df["Temperature_Air_2m_Max_24h"] - 273.15  # kelvin to celsius
print(df.head())
