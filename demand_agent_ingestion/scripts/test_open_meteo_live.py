
from datetime import date

from demand_ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoError,
)


def main() -> None:
    print("=" * 60)
    print("OPEN-METEO LIVE API TEST")
    print("=" * 60)

    try:
        with OpenMeteoClient() as client:
            records = client.fetch_historical_daily(
                location_id="LG_KOLKATA_001",
                latitude=22.5726,
                longitude=88.3639,
                start_date=date(2025, 10, 15),
                end_date=date(2025, 10, 15),
                timezone="Asia/Kolkata",
            )

        if len(records) != 1:
            raise RuntimeError(
                f"Expected one daily record, received {len(records)}."
            )

        record = records[0]

        print("\nAPI request successful.")
        print("Validated weather record:")
        print(record.model_dump_json(indent=2))
        print("\nResult: PASS")

    except OpenMeteoError as exc:
        print(f"\nOpen-Meteo ingestion failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
