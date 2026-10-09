# AgERA5 daily climate for points: agent guide

AgERA5 is ECMWF's ERA5 reanalysis corrected for agriculture: daily, global, 0.1° (~11 km), 1979 to
about a week ago. ECMWF serves it as two analysis-ready Zarr stores, so you read only the cells and
dates you need. Nothing to download first. Each day runs midnight to midnight local time, not UTC.

| Store        | URL                                                                                                                | Chunks                      | Use for                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------ | --------------------------- | ------------------------------------------------ |
| Geo-chunked  | `https://arco.datastores.ecmwf.int/cadl-arco-geo-001/arco/sis_agrometeorological_indicators/all/geoChunked.zarr`   | 2112 days × 16 lat × 32 lon | long time series at a few points or a small area |
| Time-chunked | `https://arco.datastores.ecmwf.int/cadl-arco-time-001/arco/sis_agrometeorological_indicators/all/timeChunked.zarr` | 1 day × 1024 lat × 1024 lon | maps of a region or the globe on a few days      |

Same variables, same values, different chunking. A long series from the time-chunked store, or a
whole-globe map from the geo-chunked store, touches thousands of chunks and is slow.

## API key (required)

Without a key the store returns HTTP 401. Look for one in this order, and never print or log it:

1. `CDSAPI_KEY` environment variable (or a project `.env`).
2. `~/.cdsapirc`, the standard CDS config file. The line `key: <token>` holds it.

If neither exists, tell the user how to get one. It is free and takes a few minutes:

1. Register or log in at https://cds.climate.copernicus.eu.
2. Open your profile page and copy the **Personal Access Token**.
3. Accept the dataset licence: open
   [Agrometeorological indicators from 1979 to present derived from reanalysis](https://cds.climate.copernicus.eu/datasets/sis-agrometeorological-indicators),
   go to the **Download** tab, scroll to the bottom and accept the terms. A valid key is refused
   with 401 or 403 until this is done.
4. Save the key as `CDSAPI_KEY=<token>` in `.env`, or in `~/.cdsapirc`:
   ```
   url: https://cds.climate.copernicus.eu/api
   key: <token>
   ```

Pass the key as a bearer token header. `example.py` beside this file is a working, tested call.

```python
import xarray as xr
ds = xr.open_zarr(URL, consolidated=True, chunks={},
                  storage_options={"headers": {"Authorization": f"Bearer {key}"}})
```

Needs `xarray`, `zarr`, `dask`, `fsspec`, `aiohttp`.

## Layout

- Dims `(time, latitude, longitude)`. Latitude ascends from -90 to 90, longitude from -180 to 179.9.
- Missing values are `-9999`. xarray already turns them into NaN (it is the `_FillValue`).
- The time axis trails real time by about a week.

## Variables (27; `ds.data_vars` lists them all)

| Variable                                                                                      | Units     | Note                                           |
| --------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------- |
| `Temperature_Air_2m_Max_24h` / `_Min_24h` / `_Mean_24h`                                       | K         | subtract 273.15 for °C                         |
| `Temperature_Air_2m_Max_Day_Time`, `_Min_Night_Time`, `_Mean_Day_Time`, `_Mean_Night_Time`    | K         | 06–18 / 18–06 local                            |
| `Dew_Point_Temperature_2m_Mean_24h`                                                           | K         |                                                |
| `Precipitation_Flux`                                                                          | mm d⁻¹    | daily rainfall total                           |
| `Precipitation_Duration_Fraction`, `_Rain_Duration_Fraction`, `_Solid_Duration_Fraction`      | 0–1       | share of hours with precipitation of that type |
| `Solar_Radiation_Flux`                                                                        | J m⁻² d⁻¹ | divide by 1e6 for MJ m⁻² d⁻¹                   |
| `ReferenceET_PenmanMonteith_FAO56`                                                            | mm d⁻¹    | reference evapotranspiration                   |
| `Derived_Relative_Humidity_2m_Max_24h` / `_Min_24h`, `Relative_Humidity_2m_{06,09,12,15,18}h` | %         |                                                |
| `Vapour_Pressure_Mean_24h`, `Vapour_Pressure_Deficit_at_Maximum_Temperature`                  | hPa       |                                                |
| `Wind_Speed_10m_Mean_24h`                                                                     | m s⁻¹     | at 10 m                                        |
| `Cloud_Cover_Mean_24h`                                                                        | 0–1       |                                                |
| `Snow_Thickness_Mean_24h`, `Snow_Thickness_LWE_Mean_24h`                                      | cm        | depth / liquid water equivalent                |

## Reading points efficiently

- Select only the variables and dates you need **before** picking points.
- Pick all points in **one vectorised `sel`** with `method="nearest"`, then `.compute()` once. Dask
  then fetches each needed chunk once, in parallel. Don't loop over points.
- Points closer than 0.1° share a cell. For large datasets, dedupe to unique cells first (round to
  0.1°), fetch, then join back to the points.
- Measured: 50 points × 3 variables × 2 years took 1.3 s; 5 points × 3 variables × 30 years took
  3 s; the two-point, one-year call in `example.py` takes 3 s including opening the store.

```python
import xarray as xr
V = ["Temperature_Air_2m_Max_24h", "Temperature_Air_2m_Min_24h", "Precipitation_Flux"]
pts = dict(latitude=xr.DataArray(lats, dims="pt"), longitude=xr.DataArray(lons, dims="pt"))
sub = ds[V].sel(time=slice("2021-01-01", "2022-12-31")).sel(**pts, method="nearest").compute()
df = sub.to_dataframe().reset_index()  # one row per point per day; 'pt' indexes the input
```

The returned `latitude`/`longitude` are the grid-cell centres, not the input points. Keep the
input IDs and join on `pt`.

## Other routes

- **Google Earth Engine**: `projects/climate-engine-pro/assets/ce-ag-era5-v2/daily`, curated by
  Climate Engine. Same band names and units, but 21 of the 27 variables: no derived relative
  humidity, no 09/12/18h relative humidity, no total precipitation duration fraction.
- **CDS API**: the `sis-agrometeorological-indicators` process returns NetCDF per variable and
  period. Slower, but needs only the `cdsapi` package. Use it when a Zarr read is not possible.

## Output

Convert to friendly units (°C, MJ) and use clear column names (`tmax_c`, `precip_mm`). Keep ID
columns so results join back. Daily data for many places over long periods gets big, so summarise
(season totals, heat days) when that is what is actually needed.
