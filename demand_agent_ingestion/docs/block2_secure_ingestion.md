# Block 2: Secure data ingestion

The scheduled Block 2 API paths use the Open-Meteo and Calendarific clients,
source schemas, region-coordinate loader, and weather/festival normalizers.
They add validated orchestration, MongoDB persistence, run audit, and
quarantine. The supplied historical demand file uses a separate manual loader
directly into its own collection; it is not an API source or an Airflow task.

## MongoDB

Configure `MONGO_URI` and `MONGO_DATABASE` through the process environment or
local `.env`. For authenticated deployments, set `MONGO_USERNAME`,
`MONGO_PASSWORD`, and `MONGO_AUTH_SOURCE`; the URI and password are handled as
secrets and are not logged. Use a dedicated least-privilege MongoDB user with
read/write access only to the configured database and index/collection
creation rights during schema setup. After indexes are created, production
runtime credentials can be restricted to read/write.

Each scheduled pipeline ensures indexes only for the collections it uses. The
separate historical loader ensures its own data and shared audit/quarantine
indexes. Existing collections are not dropped or recreated. The package uses:

- `historical_demand`: unique `(region_id, product_id, week_start)`.
- `weather_history`: unique `(location_id, weather_date)`.
- `weather_forecasts`: unique `(location_id, weather_date, forecast_snapshot_id)`.
- `festival_calendar`: unique `(country_code, region_code, event_date, normalized_event_name)`.
- `ingestion_runs`: unique run ID plus source/start lookup.
- `ingestion_quarantine`: unique quarantine ID plus status/run lookups.

Upserts compute deterministic document IDs from business keys, compare
content hashes excluding retrieval/run timestamps, and report inserted,
updated, unchanged, and failed writes. MongoDB retryable writes and bounded
retries for transient network/server-selection failures are enabled. A
partially failed batch is not reported as successful; failed rows can be safely
retried because writes are idempotent.

## Weather and festival ingestion

The orchestration entry points are
`demand_ingestion.ingestion.weather_ingestion.ingest_weather` and
`demand_ingestion.ingestion.festival_ingestion.ingest_festivals`. They record
each external response's source metadata in the associated `ingestion_runs`
document. Per-region API failures are isolated; persistence failures and
quarantined records affect run status and counters.

Weather reads the configured 40-row region master. On first run it fetches the
configured lookback or initial backfill range through yesterday. Subsequent
runs continue after the latest saved historical date; an explicit
`historical_start_date` argument forces a backfill. Forecast documents are
separate and each run is a distinct forecast snapshot.

Festival calls include national India data and the configured regional
`IN-WB` filter by default. The rolling context defaults to 12 months and is
translated to the required Calendarific calendar-year requests. Successful
country/region/year requests are cached using `FESTIVAL_CACHE_TTL_HOURS`.
Calendarific 429 responses honor bounded `Retry-After` or exponential backoff.

Airflow DAGs:

- `dags/weather_ingestion_dag.py` schedules weather ingestion.
- `dags/festival_ingestion_dag.py` schedules festival refreshes.

The schedules are configurable with `WEATHER_INGESTION_SCHEDULE` and
`FESTIVAL_INGESTION_SCHEDULE`. Install Apache Airflow in its supported Linux
deployment environment and install this project in that Airflow environment;
Airflow is intentionally not a core dependency of the Windows development
environment. Copy these two DAG files into the Airflow deployment's configured
DAG folder (or configure Airflow to use this repository's `dags/` directory).
Both DAGs use environment-based settings and Mongo configuration. A
`PARTIAL_SUCCESS` run is recorded and returned as a successful Airflow task;
monitor the MongoDB run audit for failed regions/contexts. There is deliberately
no scheduled historical-demand DAG.

## Independent historical demand load

This supplied file is not an external API source. It is not imported by the
weather or festival DAGs and has no periodic schedule. The manual loader
streams the configured UTF-8 comma-separated CSV (including a comma-separated
`.txt` file), maps
`region_id`, `product_id`, `week_start_date`, `week_end_date`, and `units_sold`
to the validated logical schema, and checks IDs against optional supplied
region/product allow-lists. Required IDs are non-empty; no coordinate-bearing
weather region master is required.
It quarantines rows with negative/non-integer quantities, missing fields,
malformed dates, non-seven-day ranges, IDs outside a supplied allow-list, or
duplicate source keys.
Region-product weekly continuity gaps are reported in the run audit; missing
weeks are not fabricated or filled with zero. Rejected source rows are kept in
quarantine with their original row.
Valid records retain all original CSV columns under `source_fields`, plus
validated query fields, source file/line reference, and SHA-256 source-row hash.
The original dataset is never changed. Existing records are insert-only: a
rerun does not update or overwrite an existing region-product-week document.

The duplicate-key staging index uses a temporary SQLite file so large datasets
do not require holding every source key in memory. A rerun after interruption
skips already stored business keys and does not alter their content.

Run this command manually from `demand_agent_ingestion` after configuring
MongoDB and the dataset path:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_historical_demand.py
```

The importer is not scheduled by Airflow.
`HISTORICAL_DEMAND_DATASET_PATH` is a shared settings value for this independent
loader, not an external API source setting. Its default is
`agent_demand_integrated.txt`, resolved relative to the process working
directory.

## Quarantine and operational status

Rejected records are written to `ingestion_quarantine`, including a sanitized
original record, validation errors, optional region ID, run ID, timestamp,
error category, fingerprint, and `PENDING` processing status. Controlled
status transitions are available through
`update_quarantine_status`; state updates require the caller's expected
current state to prevent concurrent reprocessing races.

Each `ingestion_runs` document records source/command, run ID, UTC start/end,
`RUNNING`/`SUCCESS`/`PARTIAL_SUCCESS`/`FAILED`, response metadata, record
counters, failed regions, and sanitized error summaries. A database write
failure cannot result in a successful run status.

## Testing and verification

Run the offline suite and linter from `demand_agent_ingestion`:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests dags scripts
```

Unit tests use mocked API clients and an in-memory Mongo-compatible fake. They
verify orchestration, cache/idempotency behavior, unique index definitions,
quarantine transitions, partial regional failures, and import resumption.
They do not verify a live MongoDB deployment, actual Airflow scheduler/task
execution, or live external API credentials. Those deployment integrations
must be checked in the configured runtime environment.

## Current operational prerequisites and limitations

- The repository has no authoritative coordinate-bearing region master.
  Weather regional API ingestion requires one; the independent historical
  importer does not.
- Product master validation is optional because no product master currently
  exists; product IDs are otherwise preserved from the historical file.
- Airflow and live MongoDB are not installed/configured in this developer
  environment. Their DAG parse/scheduler behavior and real database writes
  remain deployment verification tasks.
- API availability, subscription limits, external data completeness, MongoDB
  access policies, and production credential handling depend on deployment
  configuration.
