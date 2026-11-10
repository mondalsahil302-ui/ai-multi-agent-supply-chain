import csv

import pytest

from demand_ingestion.historical_demand import (
    DatasetDiscoveryError,
    discover_dataset,
    profile_dataset,
)

HEADER = [
    "region_product_week_key",
    "region_id",
    "region_of_kolkata",
    "product_id",
    "product_name",
    "week_start_date",
    "week_end_date",
    "units_sold",
]


def write_dataset(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def test_dataset_discovery_detects_comma_separated_text(tmp_path):
    dataset = tmp_path / "demand.txt"
    write_dataset(
        dataset,
        HEADER,
        [["key", "KOL-LOC-001", "Lake Gardens", "P-001", "Milk",
          "2024-01-01", "2024-01-07", "12"]],
    )

    descriptor = discover_dataset(dataset)

    assert descriptor.file_format == "delimited_text"
    assert descriptor.delimiter == ","
    assert descriptor.columns == HEADER


def test_schema_profile_identifies_weekly_demand_fields(tmp_path):
    dataset = tmp_path / "demand.csv"
    write_dataset(
        dataset,
        HEADER,
        [
            ["key1", "KOL-LOC-001", "Lake Gardens", "P-001", "Milk",
             "2024-01-01", "2024-01-07", "12"],
            ["key2", "KOL-LOC-002", "Garia", "P-001", "Milk",
             "2024-01-08", "2024-01-14", "15"],
        ],
    )

    profile = profile_dataset(dataset)

    assert profile.required_columns_present is True
    assert profile.weekly_granularity is True
    assert profile.row_count == 2
    assert profile.region_count == 2
    assert profile.product_count == 1
    assert profile.start_date.isoformat() == "2024-01-01"
    assert profile.end_date.isoformat() == "2024-01-14"
    assert profile.schema_roles["units_sold"] == "weekly unit demand"


def test_missing_required_columns_are_reported(tmp_path):
    dataset = tmp_path / "partial.csv"
    write_dataset(dataset, ["region_id", "product_id"], [["R1", "P1"]])

    profile = profile_dataset(dataset)

    assert profile.required_columns_present is False
    assert profile.missing_required_columns == [
        "week_start_date",
        "week_end_date",
        "units_sold",
    ]


def test_invalid_dates_and_non_weekly_ranges_are_reported(tmp_path):
    dataset = tmp_path / "invalid.csv"
    write_dataset(
        dataset,
        HEADER,
        [
            ["key1", "R1", "One", "P1", "Product",
             "not-a-date", "2024-01-07", "4"],
            ["key2", "R1", "One", "P1", "Product",
             "2024-01-08", "2024-01-15", "4"],
        ],
    )

    profile = profile_dataset(dataset)

    assert profile.invalid_date_rows == 1
    assert profile.weekly_granularity is False
    assert any("seven days" in issue for issue in profile.issues)


def test_empty_dataset_is_reported(tmp_path):
    dataset = tmp_path / "empty.csv"
    dataset.write_text("", encoding="utf-8")

    profile = profile_dataset(dataset)

    assert profile.row_count == 0
    assert profile.weekly_granularity is False
    assert "Dataset contains no demand records." in profile.issues


def test_incorrect_dataset_path_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        discover_dataset(tmp_path / "missing.csv")


def test_non_utf8_dataset_is_reported(tmp_path):
    dataset = tmp_path / "invalid.csv"
    dataset.write_bytes(b"\xff\xfe")

    with pytest.raises(DatasetDiscoveryError, match="UTF-8"):
        discover_dataset(dataset)
