# Demand Agent Normalization Layer Design

## 1. Overview & Architectural Role

The Normalization Layer provides deterministic validation, canonical schema transformation, duplicate reconciliation, quarantine isolation, and weekly temporal projections for external weather and festival data ingested by the **Demand Agent**.

Situated directly between raw API client adapters (`OpenMeteoClient`, `CalendarificClient`) and future MongoDB persistence, this layer ensures that downstream forecasting models, inventory optimizers, and autonomous agents consume verified, structured, and leak-free data.

```
       +----------------------------+       +-----------------------------+
       |   Open-Meteo API Client    |       |  Calendarific API Client    |
       +----------------------------+       +-----------------------------+
                     |                                     |
                     v                                     v
       +----------------------------+       +-----------------------------+
       | WeatherDailyRecord Models  |       |    FestivalRecord Models    |
       +----------------------------+       +-----------------------------+
                     \                                     /
                      \                                   /
                       v                                 v
          +===================================================+
          |            DEMAND NORMALIZATION LAYER             |
          |  - Canonical schemas & strict type coercion       |
          |  - Location & coordinate tolerance validation     |
          |  - Forecast snapshot integrity & key segregation  |
          |  - Content fingerprinting & duplicate arbitration |
          |  - Structured quarantine with secret scrubbing    |
          |  - Sunday-Saturday weekly derived projections     |
          |  - Batch reconciliation & operational audit trail |
          +===================================================+
                    /                  |                  \
                   v                   v                   v
        +--------------------+ +----------------+ +--------------------+
        | Normalized Records | | Weekly Summary | | Quarantine Records |
        |   (Daily/Event)    | |  Projections   | |  (Audit & Triage)  |
        +--------------------+ +----------------+ +--------------------+
                   \                   |                   /
                    v                  v                  v
          +===================================================+
          |      FUTURE PERSISTENCE (MongoDB Collections)     |
          +===================================================+
```

---

## 2. Canonical Contracts & Record Models

The normalization layer establishes explicit, immutable Pydantic v2 schemas:

### 2.1 Normalized Weather Record (`NormalizedWeatherRecord`)
- **Grain**: Location $\times$ Date $\times$ Data Kind ($\times$ Forecast Snapshot ID if forecast).
- **Record Identity (`record_id`)**: Deterministic SHA-256 fingerprint generated from canonical business key.
- **Fields**:
  - `schema_version`: Fixed literal `"v1"`.
  - `record_id`: SHA-256 hash (64 hex characters).
  - `location_id`: Standard canonical location identifier (e.g., `KOL-LOC-001`).
  - `latitude`, `longitude`: Validated geographic coordinates within configured tolerance.
  - `weather_date`: ISO calendar date (`YYYY-MM-DD`).
  - `data_kind`: Literal `"historical"` or `"forecast"`.
  - `forecast_snapshot_id`: Null for historical observations; ISO timestamp or unique run tag for forecasts.
  - `forecast_issued_at_utc`: UTC timestamp when provider issued the forecast.
  - `temperature_mean_c`, `temperature_min_c`, `temperature_max_c`: Temperatures in Celsius, strictly validated (`min <= mean <= max`).
  - `rainfall_mm`: Non-negative precipitative depth in millimetres.
  - `humidity_mean_pct`: Relative humidity bounded strictly in $[0.0, 100.0]\%$.
  - `weather_code`: Integer WMO code (`0` to `99`).
  - `coverage_hours`: Hours represented by measurement (typically 24).
  - `source`: Literal `"open_meteo"`.
  - `retrieved_at_utc`: UTC timestamp of client ingestion.

### 2.2 Normalized Festival Record (`NormalizedFestivalRecord`)
- **Grain**: Country $\times$ Target Year $\times$ Deterministic Event Key.
- **Record Identity (`record_id`)**: Inherited directly from `FestivalRecord.event_key` (SHA-256 hash).
- **Regional Applicability**: Strictly derived from provider fields (`"national"`, `"regional"`, or `"unknown"`). Never invents speculative weights or synthetic Kolkata multipliers.
- **Fields**:
  - `schema_version`: Fixed literal `"v1"`.
  - `record_id`: Deterministic SHA-256 hash.
  - `country_code`: Standard ISO 3166-1 alpha-2 uppercase country code (e.g., `"IN"`).
  - `event_name`: Cleaned, trimmed event title.
  - `event_date`: ISO calendar date.
  - `target_year`: Verified calendar year.
  - `description`, `canonical_url`: Normalized optional text (empty strings converted to `None`).
  - `event_types`: Deduplicated, casefold-sorted array of event tags.
  - `primary_type`: Normalized primary categorization.
  - `locations`, `states`: Raw regional text preserved verbatim for auditability.
  - `regional_applicability`: Provider-governed scope (`"national"`, `"regional"`, `"unknown"`).
  - `source`: Literal `"calendarific"`.
  - `retrieved_at_utc`: Timezone-aware UTC retrieval timestamp.

---

## 3. Daily Source Grain vs. Weekly Projections

A central architectural requirement is the strict segregation of **source records** from **derived projections**:

1. **Daily / Event Level**:
   - Normalized weather and festival records preserve individual daily and event granularity.
   - Raw observations are never pre-aggregated or permanently merged.
2. **Weekly Projections (`WeeklyWeatherSummary` & `WeeklyFestivalProjection`)**:
   - Generated as distinct downstream projection entities.
   - Project calendar weeks run strictly from **Sunday through Saturday** (matching `Datasets/standardized/std_calendar_week.csv`).
   - If an authoritative `CalendarRegistry` is provided, project weeks map directly to standard canonical `week_id` identifiers (e.g., `W002`); otherwise, standard Sunday-Saturday date bounds are calculated deterministically.
3. **Aggregation Mathematics**:
   - $\text{temperature\_mean\_c} = \text{arithmetic mean of daily means}$
   - $\text{temperature\_min\_c} = \text{minimum of daily minimums}$
   - $\text{temperature\_max\_c} = \text{maximum of daily maximums}$
   - $\text{rainfall\_total\_mm} = \text{sum of daily rainfall measurements}$
   - $\text{humidity\_mean\_pct} = \text{arithmetic mean of daily relative humidities}$
   - $\text{weather\_code\_counts} = \text{frequency dictionary of WMO codes (e.g., } \{61: 3, 0: 4\} \text{)}$. **WMO codes are categorical and are never averaged.**

---

## 4. Duplicate Detection & Quarantine Mechanics

The normalization layer employs deterministic content hashing to distinguish identical duplicates from conflicting duplicates:

### 4.1 Identical Duplicates
- **Condition**: Two or more records share the identical business key **and** identical measurement content hash.
- **Action**: One canonical instance is accepted; duplicates are silently collapsed.
- **Accounting**: Increments `identical_duplicates` on `BatchNormalizationReport`.

### 4.2 Conflicting Duplicates
- **Condition**: Two or more records share the identical business key **but** exhibit differing measurement values (e.g. differing mean temperatures, differing event descriptions).
- **Action**: **All** instances sharing the conflicting key are rejected and routed to quarantine.
- **Accounting**: Increments `conflicting_duplicates` on `BatchNormalizationReport`.
- **Reason**: Silent overwrites or arbitrary "last-write-wins" policies introduce silent data corruption. Conflicting records require operator triage.

### 4.3 Structured Quarantine Record (`QuarantineRecord`)
Any record failing structural validation, location boundary checks, date constraints, or duplicate resolution is isolated in a structured quarantine record:
- `quarantine_id`: Unique tracking UUID.
- `source_system`: Source API provider (`open_meteo` or `calendarific`).
- `record_type`: Data category (`weather` or `festival`).
- `error_category`: Strongly typed category (`VALIDATION_ERROR`, `COORDINATE_OUT_OF_BOUNDS`, `UNKNOWN_LOCATION`, `LOCATION_COORDINATE_MISMATCH`, `DATE_OUT_OF_RANGE`, `CONFLICTING_DUPLICATE`).
- `error_message`: Sanitized descriptive diagnosis.
- `raw_payload`: Scrubbed JSON payload.
- `payload_fingerprint`: SHA-256 hash of original payload.
- `quarantined_at_utc`: Timezone-aware UTC timestamp.
- `ingestion_run_id`: Airflow DAG or pipeline execution run ID.

> [!IMPORTANT]
> **Secret Redaction**: Every raw payload passed into `create_quarantine_record` is sanitized by `sanitize_payload`, recursively masking API keys, bearer tokens, passwords, and private authorization headers with `***REDACTED***`.

---

## 5. Location and Temporal Validation

### 5.1 Location Registry (`LocationRegistry`)
- Validates `location_id` against reference metadata.
- Implements geodesic tolerance checking: verifies incoming latitude and longitude against expected coordinates within a configurable tolerance (default $0.05^\circ \approx 5.5\text{ km}$).
- Enforces strict or permissive registration modes.

### 5.2 Temporal Rules & Sunday-through-Saturday Calendar
- In accordance with project standards, the weekly cycle begins on Sunday ($d.weekday() = 6$) and ends on Saturday ($d.weekday() = 5$).
- `CalendarRegistry.compute_project_week_bounds(target_date)` computes the exact start and end dates:
  $$\text{offset} = (d.\text{weekday}() + 1) \bmod 7$$
  $$\text{start\_date} = d - \text{timedelta}(\text{days}=\text{offset})$$
  $$\text{end\_date} = \text{start\_date} + \text{timedelta}(\text{days}=6)$$

### 5.3 Forecast Snapshot Integrity
- Forecasts frequently revise predictions for the same future calendar date over successive model runs.
- To prevent later forecast snapshots from clobbering earlier snapshots, the `forecast_snapshot_id` (or `forecast_issued_at_utc`) is explicitly embedded into the business key:
  $$\text{Business Key} = \text{open\_meteo}:\{\text{location\_id}\}:\{\text{weather\_date}\}:\text{forecast}:\{\text{forecast\_snapshot\_id}\}$$
- Historical observations and forecast snapshots are strictly isolated into separate weekly summaries.

---

## 6. Batch Operational Reconciliation

Every batch execution produces a `BatchNormalizationReport` that mathematically accounts for every input record:

$$\text{input\_records} = \text{accepted\_records} + \text{identical\_duplicates} + \text{conflicting\_duplicates} + \text{validation\_failures}$$
$$\text{rejected\_records} = \text{conflicting\_duplicates} + \text{validation\_failures}$$

Any discrepancy in this balance triggers an immediate `ValueError`, guaranteeing zero unmonitored record loss during pipeline execution.

---

## 7. Future MongoDB Persistence Integration

When persistence is implemented, MongoDB collections will consume normalized records as follows:

| Collection | Canonical Business Key / Unique Index | Projection / Mutation Rule |
| :--- | :--- | :--- |
| `weather_daily` | `{location_id: 1, weather_date: 1, data_kind: 1, forecast_snapshot_id: 1}` | Idempotent upsert (`$setOnInsert`) |
| `weather_weekly` | `{location_id: 1, period_start_date: 1, data_kind: 1, forecast_snapshot_id: 1}` | Replaced upon recalculation |
| `festival_events` | `{country_code: 1, event_date: 1, record_id: 1}` | Idempotent upsert |
| `festival_weekly` | `{country_code: 1, period_start_date: 1}` | Replaced upon recalculation |
| `quarantine_sink` | `{quarantine_id: 1}` (Index on `{error_category: 1, quarantined_at_utc: -1}`) | Append-only audit sink |

