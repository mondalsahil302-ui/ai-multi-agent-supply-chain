import csv

import pytest

from demand_ingestion.data_sources.region_master import (
    RegionMasterError,
    load_region_master,
)


def write_regions(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["region_id", "region_name", "latitude", "longitude"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_loads_region_master_coordinates(tmp_path):
    path = tmp_path / "regions.csv"
    write_regions(
        path,
        [
            {
                "region_id": "KOL-LOC-001",
                "region_name": "North",
                "latitude": "22.5",
                "longitude": "88.3",
            }
        ],
    )

    regions = load_region_master(path)

    assert regions[0].region_id == "KOL-LOC-001"
    assert regions[0].region_name == "North"
    assert regions[0].latitude == 22.5


def test_invalid_coordinates_and_duplicates_are_rejected(tmp_path):
    path = tmp_path / "regions.csv"
    write_regions(
        path,
        [
            {
                "region_id": "R1",
                "region_name": "",
                "latitude": "91",
                "longitude": "88",
            }
        ],
    )
    with pytest.raises(RegionMasterError, match="Invalid region master"):
        load_region_master(path)

    write_regions(
        path,
        [
            {
                "region_id": "R1",
                "region_name": "",
                "latitude": "22",
                "longitude": "88",
            },
            {
                "region_id": "R1",
                "region_name": "",
                "latitude": "23",
                "longitude": "89",
            },
        ],
    )
    with pytest.raises(RegionMasterError, match="Duplicate region_id"):
        load_region_master(path)


def test_missing_region_master_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_region_master(tmp_path / "missing.csv")


def test_empty_region_master_is_reported(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(RegionMasterError, match="empty"):
        load_region_master(path)
