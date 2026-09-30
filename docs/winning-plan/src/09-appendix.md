# Appendix — Fields the tasks must use

Dates are `YYYY-MM-DD` and timestamps are UTC. Missing values are `null`. The perfected plan
adds the fields below so a judge can distinguish a source observation from an estimate or an
export gap. Do not infer pass, cloud, no-pass, burned area, or fire-free status from a missing
row.

## Aggregates (`fireatlas-daily-aggregates-v1`)

Top level: `schema`, `method_version`, `region` (`id`, `bbox`), `generated_utc`, `inputs` (file
name, request metadata, retrieval date, and `sha256`), `days`. Each day: `date`, and for
`MODIS_SP` and `VIIRS_SNPP_SP`: `cells`, `raw`, `frp_sum`, `excluded`, and
`excluded_type_counts`, plus a `sensor_bridge` object with its method version, common-grid
counts and mismatch state. The full daily aggregate response additionally records native
pixel size, the centroid-to-EASE-Grid-1km method, eligible and excluded row counts, FRP
valid/missing rows, product versions, and source hashes. Keep VIIRS 375 m detail rows
separately inspectable. A documented outage can leave FRP unknown; it is never silently shown
as zero.

## Calibration (`fireatlas-calibration-v1`)

Top level: `schema`, `region`, `overlap` start and end, `bootstrap` replicates `1000` and seed `20261114`, `ratio_by_month` (`month`, `r`, `r_lo`, `r_hi`, `basis`), `loyo` with `month_of_year`, `single_ratio`, and `no_harmonization` (each has `median_abs_log_error`), and `selected_model`.

## Calendar (`fireatlas-calendar-v2`)

`meta`: `region`, `bbox`, `unit` = `VIIRS-equivalent active-fire cell-days on a common 1 km
grid`, `native_detail`, `bridge_method_version`, `frp_context`, `corroboration`, `baseline`
(`years_used`, `excluded`), `calibration_id`, `data_class`, and source inputs/hashes. `days`:
`date`, `value`, `low`, `high`, `estimate_type` (`observed` or `scaled`), `source_used`,
`quality`, `evidence_state` (`observed`, `scaled`, `unknown`, or `complete_zero_export`),
`coverage_state` (`observed`, `unknown`, `documented_processing_gap`, or
`complete_zero_export`), `sensor_bridge`, `frp_mw_day`, source-specific raw cells/pixels/FRP,
and the reason. A scaled outage day therefore carries both `evidence_state=scaled` and
`coverage_state=documented_processing_gap`. `months`: `month`, `value`, `percentile_rank`,
`rank`, `n_years`, `flag`, `degraded_days`, `unknown_days`, `season_start`, `season_peak`,
`season_end`, `season_status`.

## Notices

`id`, `source_id`, `start_utc`, `end_utc`, `url`, `retrieved_utc`, `quote`, and the affected
product/version. A notice marks a documented processing gap; it does not prove no pass or no
fire.
