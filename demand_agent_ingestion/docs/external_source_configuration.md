# External source configuration

Copy the repository-root `.env.example` to `.env` and set values for the local
environment. `Settings` reads environment variables first and then `.env`
relative to the process working directory. Do not commit `.env`.

| Variable | Default | Description |
|---|---|---|
| `OPEN_METEO_BASE_URL` | `https://api.open-meteo.com/v1/forecast` | Open-Meteo forecast endpoint |
| `OPEN_METEO_ARCHIVE_URL` | `https://archive-api.open-meteo.com/v1/archive` | Open-Meteo historical endpoint |
| `CALENDARIFIC_BASE_URL` | `https://calendarific.com/api/v2/holidays` | Calendarific holidays endpoint |
| `CALENDARIFIC_API_KEY` | unset | Calendarific API credential; required for requests |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` | Timezone used for weather dates and forecasts |
| `DEFAULT_COUNTRY` | `IN` | Default Calendarific country |
| `DEFAULT_REGION_CODE` | `IN-WB` | West Bengal Calendarific region to pass when supported |
| `DEFAULT_FORECAST_DAYS` | `7` | Forecast horizon, from 1 to 16 days |
| `REGION_MASTER_DATASET_PATH` | `region_master.csv` | Authoritative CSV containing region coordinates |
| `HTTP_TIMEOUT_SECONDS` | `20` | HTTP timeout |
| `HTTP_MAX_RETRIES` | `3` | Number of retries after the initial request |
| `HTTP_BACKOFF_MAX_SECONDS` | `30` | Maximum exponential retry delay |

The region-master path may be absolute or relative to the process working
directory. The repository currently has no coordinate-bearing region master.
Do not derive or guess coordinates from region names; supply an authoritative
file with columns `region_id,latitude,longitude` and optionally `region_name`
before requesting regional weather.

Historical-demand file configuration and import are deliberately separate
from external API configuration; see
[`block2_secure_ingestion.md`](block2_secure_ingestion.md#independent-historical-demand-import).

## Calendarific authentication

Create an API key in the Calendarific account and set it in the local `.env`:

```dotenv
CALENDARIFIC_API_KEY=your_account_key
```

The value is loaded as a secret, sent only as the API's `api_key` request
parameter, and excluded from application error text and logs. A missing or
invalid key is reported as a typed error; never paste credentials into code,
tests, issue reports, or command output.

For India-wide holidays request `country_code="IN"`. Where the account/API
supports a regional filter, pass `location="IN-WB"` for West Bengal. Regional
and national requests are separate source calls.

## Smoke checks

The offline test suite uses mocked responses:

```powershell
cd demand_agent_ingestion
.\.venv\Scripts\python.exe -m pytest
```

The scripts under `scripts/test_*_live.py` are optional and make live requests.
Calendarific's script requires a valid key. A live result is confirmed only
when the corresponding script completes successfully; unit-test success is
not evidence of Internet/API availability.
