# External API source support

The external source adapters are `demand_ingestion.open_meteo_client` and
`demand_ingestion.calendarific_client`. The `data_sources` package provides
region-master loading needed by regional Open-Meteo calls; it does not register
or expose the historical demand dataset as an API source.

## Region coordinates

`demand_ingestion.data_sources.region_master.load_region_master` reads a
configured UTF-8 CSV with `region_id` (or `location_id`), `latitude`, and
`longitude` columns. An optional `region_name` or `region_of_kolkata` column
provides a display name. Coordinates are validated and are never hard-coded in
the API client.

The historical demand dataset contains region IDs but no coordinates. It is
loaded through the independent `demand_ingestion.historical_demand` path and
does not feed the scheduled weather or festival DAGs.

For adapter details, source metadata, authentication, and environment settings,
see [`external_source_configuration.md`](../../../docs/external_source_configuration.md).
