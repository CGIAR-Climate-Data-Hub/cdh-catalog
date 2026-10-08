"""Read NASA POWER daily values for a few points from the Zarr stores on AWS Open Data.

No account or key. Needs:
  pip install xarray zarr s3fs dask
  python example.py
"""

import pandas as pd
import xarray as xr

# "temporal" stores = small spatial tiles, long time runs: cheap for long series at a few points.
# Swap "temporal" for "spatial" (one day per chunk) when you want a map on a few days.
# MERRA-2 runs 1981 to about a month ago; GEOS-IT (2022 onward, same grid and variable names)
# fills the gap to a few days ago. The API does this join for you; here we do it by hand.
MERRA2 = "s3://nasa-power/merra2/temporal/power_merra2_daily_temporal_lst.zarr"
GEOSIT = "s3://nasa-power/geosit/temporal/power_geosit_daily_temporal_lst.zarr"


def open_store(url: str) -> xr.Dataset:
    return xr.open_zarr(url, consolidated=True, chunks={}, storage_options={"anon": True})


variables = ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
lats = [-1.29, 9.03]  # Nairobi, Addis Ababa
lons = [36.82, 38.74]
points = dict(lat=xr.DataArray(lats, dims="pt"), lon=xr.DataArray(lons, dims="pt"))

start, end = "2026-06-01", pd.Timestamp.today().strftime("%Y-%m-%d")

# Pick variables and dates first, then all points in one vectorised sel, then compute once.
merra2 = open_store(MERRA2)[variables].sel(time=slice(start, end)).sel(**points, method="nearest").compute()
# The time axis is allocated years ahead; drop the all-NaN days past the last available date.
merra2 = merra2.dropna("time", how="all")

# Only fetch GEOS-IT for the days MERRA-2 does not have yet.
after = (merra2.time[-1] + pd.Timedelta(days=1)).values if merra2.time.size else start
geosit = open_store(GEOSIT)[variables].sel(time=slice(after, end)).sel(**points, method="nearest").compute()
geosit = geosit.dropna("time", how="all")

ds = xr.concat([merra2, geosit], dim="time")
df = ds.to_dataframe().reset_index().rename(columns={"T2M_MAX": "tmax_c", "T2M_MIN": "tmin_c", "PRECTOTCORR": "precip_mm"})
print(f"MERRA-2 to {str(merra2.time[-1].values)[:10]}, GEOS-IT to {str(geosit.time[-1].values)[:10]}")
print(df.tail())
