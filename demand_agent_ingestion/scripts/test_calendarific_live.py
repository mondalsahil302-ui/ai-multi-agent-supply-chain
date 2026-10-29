from demand_ingestion.calendarific_client import (
    CalendarificClient,
    CalendarificError,
)
from demand_ingestion.config import get_settings


def main() -> None:
    settings = get_settings()
    api_key = settings.calendarific_api_key

    if api_key is None or not api_key.get_secret_value().strip():
        raise SystemExit(
            "Calendarific key is missing. Configure it in .env."
        )

    print("=" * 55)
    print("CALENDARIFIC LIVE API TEST")
    print("=" * 55)

    try:
        with CalendarificClient(settings=settings) as client:
            records = client.fetch_holidays(
                country_code="IN",
                year=2026,
            )

        print("\nAPI request successful.")
        print("Country: India (IN)")
        print("Year: 2026")
        print(f"Validated festival records: {len(records)}")

        print("\nFirst five records:")

        for record in records[:5]:
            print(
                f"- {record.event_date.isoformat()} | "
                f"{record.event_name} | "
                f"Types: {', '.join(record.event_types) or 'Not provided'}"
            )

        print("\nResult: PASS")

    except CalendarificError as exc:
        print(f"\nCalendarific request failed: {exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()