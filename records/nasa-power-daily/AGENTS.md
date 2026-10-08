# NASA POWER daily weather for points: agent guide

NASA POWER packages NASA models and satellite products into free, no-login daily weather, solar
radiation and precipitation, global, 1981 to a few days ago. The primary route is a set of Zarr
stores on AWS Open Data, one per source, so you read only the cells and dates you need. Nothing to
download first, no key, no account.

## Sources and stores

| Source    | Covers                                   | Grid          | Period                   | Variables       |
| --------- | ---------------------------------------- | ------------- | ------------------------ | --------------- |
| merra2    | meteorology (T, RH, wind, P, soil, snow) | 0.5° × 0.625° | 1981 to ~1 month ago     | 74              |
| geosit    | same, near-real-time                     | 0.5° × 0.625° | 2022 to ~3 days ago      | 72 (same names) |
| syn1deg   | solar and longwave radiation             | 1°            | 2001 to ~3 months ago    | 47              |
| flashflux | radiation, near-real-time                | 1°            | 2024 to ~5 days ago      | 5               |
| imerg     | satellite precipitation                  | 0.1°          | 1998 to ~2 days ago, UTC | 3               |

Store URL pattern, anonymous S3 in `us-west-2`:

```
s3://nasa-power/{source}/{temporal|spatial}/power_{source}_daily_{temporal|spatial}_{lst|utc}.zarr
```

- `temporal` chunks are long in time and small in space (MERRA-2: 5844 days × 15 × 15 cells).
  Use for time series at points or a small area.
- `spatial` chunks are one day of the whole grid. Use for maps on a few days. A long series from a
  spatial store, or a global map from a temporal store, touches thousands of chunks and is slow.
- `lst` days run midnight to midnight local solar time; `utc` is also available for every source
  except IMERG, which is UTC only.

Read the newest day per store from `https://nasa-power.s3.us-west-2.amazonaws.com/last_available.json`.

## Opening a store

```python
import xarray as xr
ds = xr.open_zarr(URL, consolidated=True, chunks={}, storage_options={"anon": True})
```

Needs `xarray`, `zarr`, `s3fs`, `dask`. `example.py` beside this file is a working, tested call.

## Layout and gotchas

- Dims `(time, lat, lon)`. Latitude ascends. MERRA-2 and GEOS-IT longitudes run -180 to 179.375.
- Missing values are NaN already. The API uses -999 instead.
- **Time axes are allocated to 2029-12-31.** Everything past the last available day is NaN. Slice
  by date and `dropna("time", how="all")`; never trust `ds.time[-1]`.
- Units are the source's: temperature °C, precipitation mm per day, radiation W m-2 as a daily
  mean. The API's AG community converts radiation to MJ m-2 per day (multiply W m-2 by 0.0864).
- Variable `attrs` carry `units` and `long_name`; the record's data dictionary has the definitions.

## Joining sources for "1981 to today"

Each source is its own store. For a full series at a point, read MERRA-2 to its last valid day,
then GEOS-IT from the next day on; same for SYN1deg then FLASHFlux. `example.py` shows the join.
The two models differ slightly, so do not read a trend across the join; for trends use MERRA-2
alone and accept the lag.

## Reading points efficiently

- Select only the variables and dates you need **before** picking points.
- Pick all points in **one vectorised `sel`** with `method="nearest"`, then `.compute()` once.
  Don't loop over points.
- Points closer than a cell share values. For many points, dedupe to unique cells first, fetch,
  then join back.
- Measured: two points × three variables × four months across both stores took 10 s including
  opening the stores.

```python
V = ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
pts = dict(lat=xr.DataArray(lats, dims="pt"), lon=xr.DataArray(lons, dims="pt"))
sub = ds[V].sel(time=slice("2021-01-01", "2022-12-31")).sel(**pts, method="nearest").compute()
df = sub.dropna("time", how="all").to_dataframe().reset_index()
```

The returned `lat`/`lon` are grid-cell centres, not the input points. Keep input IDs and join on `pt`.

## Common variables

| Variable                          | Units     | Note                                       |
| --------------------------------- | --------- | ------------------------------------------ |
| `T2M`, `T2M_MAX`, `T2M_MIN`       | °C        | daily mean, max, min at 2 m                |
| `T2MDEW`, `T2MWET`                | °C        | dew point, wet bulb                        |
| `RH2M`, `QV2M`                    | %, g kg-1 | relative, specific humidity                |
| `PRECTOTCORR`                     | mm d-1    | MERRA-2 bias-corrected precipitation       |
| `IMERG_PRECTOT`                   | mm d-1    | satellite precipitation (imerg store, UTC) |
| `WS2M`, `WS10M`                   | m s-1     | wind speed                                 |
| `PS`                              | hPa       | surface pressure                           |
| `GWETTOP`, `GWETROOT`, `GWETPROF` | 0–1       | soil wetness: surface, root zone, profile  |
| `TSOIL1`…`TSOIL6`                 | °C        | soil temperature by layer                  |
| `ALLSKY_SFC_SW_DWN`               | W m-2     | solar radiation (syn1deg / flashflux)      |
| `ALLSKY_SFC_PAR_TOT`              | W m-2     | photosynthetically active radiation        |
| `ALLSKY_SFC_LW_DWN`               | W m-2     | downward longwave                          |

## The API instead

`https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,PRECTOTCORR&community=AG&latitude=-1.29&longitude=36.82&start=20240101&end=20241231&format=JSON`

One GET per point, sources already joined, JSON/CSV/NetCDF. Good for a handful of points or when
Zarr is not possible. Add `time-standard=UTC` for IMERG parameters. Slow and rate-limited for many
points or large regions; use the stores for those.

## Output

Convert to friendly column names (`tmax_c`, `precip_mm`). Keep ID columns so results join back.
Daily data for many places over long periods gets big, so summarise (season totals, heat days)
when that is what is actually needed.
