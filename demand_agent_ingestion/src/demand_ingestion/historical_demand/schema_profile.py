import csv
import math
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from demand_ingestion.config import Settings
from demand_ingestion.historical_demand.dataset_discovery import (
    DatasetDescriptor,
    discover_dataset,
)

REQUIRED_COLUMNS = (
    "region_id",
    "product_id",
    "week_start_date",
    "week_end_date",
    "units_sold",
)

SCHEMA_ROLES = {
    "week_start_date": "week start date",
    "week_end_date": "week end date",
    "region_id": "region identifier",
    "region_of_kolkata": "region display name",
    "product_id": "product identifier",
    "product_name": "product display name",
    "units_sold": "weekly unit demand",
    "sales_value_rs": "weekly sales value in Indian rupees",
    "stockout_flag": "stockout indicator",
    "holiday_flag": "holiday indicator",
    "temperature_c": "temperature in Celsius",
    "rainfall_mm": "rainfall in millimeters",
}


class HistoricalDemandProfile(BaseModel):
    """Non-mutating summary of the product-region weekly input dataset."""

    model_config = ConfigDict(extra="forbid")

    dataset: DatasetDescriptor
    row_count: int
    columns: list[str]
    required_columns_present: bool
    missing_required_columns: list[str]
    region_count: int
    region_ids: list[str]
    expected_region_count: int
    region_coverage_complete: bool
    product_count: int
    start_date: date | None
    end_date: date | None
    weekly_granularity: bool
    invalid_date_rows: int
    invalid_demand_rows: int
    malformed_rows: int
    schema_roles: dict[str, str]
    issues: list[str]


def profile_dataset(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> HistoricalDemandProfile:
    """Inspect dataset schema and weekly coverage without importing its rows."""

    descriptor = discover_dataset(path, settings=settings)
    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in descriptor.columns
    ]
    issues: list[str] = []
    if missing:
        issues.append(f"Missing required columns: {', '.join(missing)}")

    row_count = 0
    invalid_date_rows = 0
    invalid_demand_rows = 0
    malformed_rows = 0
    regions: set[str] = set()
    products: set[str] = set()
    first_date: date | None = None
    last_date: date | None = None
    invalid_week_lengths = 0
    required_date_columns_present = {
        "week_start_date",
        "week_end_date",
    }.issubset(descriptor.columns)

    if descriptor.columns:
        try:
            with Path(descriptor.path).open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as stream:
                reader = csv.DictReader(
                    stream,
                    delimiter=descriptor.delimiter,
                )
                for row in reader:
                    row_count += 1
                    if None in row:
                        malformed_rows += 1

                    region = (row.get("region_id") or "").strip()
                    product = (row.get("product_id") or "").strip()
                    if region:
                        regions.add(region)
                    if product:
                        products.add(product)

                    start = _parse_date(row.get("week_start_date"))
                    end = _parse_date(row.get("week_end_date"))
                    if start is None or end is None:
                        invalid_date_rows += 1
                    else:
                        first_date = start if first_date is None else min(first_date, start)
                        last_date = end if last_date is None else max(last_date, end)
                        if (end - start).days != 6:
                            invalid_week_lengths += 1

                    demand = (row.get("units_sold") or "").strip()
                    try:
                        if not demand:
                            raise ValueError
                        if not math.isfinite(float(demand)) or float(demand) < 0:
                            raise ValueError
                    except ValueError:
                        invalid_demand_rows += 1
        except UnicodeDecodeError as exc:
            raise ValueError(
                "Historical demand dataset must be UTF-8 encoded."
            ) from exc

    if row_count == 0:
        issues.append("Dataset contains no demand records.")
    if invalid_date_rows:
        issues.append(f"{invalid_date_rows} row(s) have invalid weekly dates.")
    if invalid_week_lengths:
        issues.append(f"{invalid_week_lengths} row(s) do not span seven days.")
    if invalid_demand_rows:
        issues.append(f"{invalid_demand_rows} row(s) have invalid units_sold.")
    if malformed_rows:
        issues.append(f"{malformed_rows} row(s) have extra delimited fields.")
    if len(regions) != 40:
        issues.append(
            f"Dataset has {len(regions)} region(s); expected 40 configured regions."
        )

    return HistoricalDemandProfile(
        dataset=descriptor,
        row_count=row_count,
        columns=descriptor.columns,
        required_columns_present=not missing,
        missing_required_columns=missing,
        region_count=len(regions),
        region_ids=sorted(regions),
        expected_region_count=40,
        region_coverage_complete=len(regions) == 40,
        product_count=len(products),
        start_date=first_date,
        end_date=last_date,
        weekly_granularity=(
            row_count > 0
            and required_date_columns_present
            and invalid_date_rows == 0
            and invalid_week_lengths == 0
        ),
        invalid_date_rows=invalid_date_rows,
        invalid_demand_rows=invalid_demand_rows,
        malformed_rows=malformed_rows,
        schema_roles={
            column: role
            for column, role in SCHEMA_ROLES.items()
            if column in descriptor.columns
        },
        issues=issues,
    )


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        normalized = value.strip()
        parsed = date.fromisoformat(normalized)
        return parsed if parsed.isoformat() == normalized else None
    except ValueError:
        return None
