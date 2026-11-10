import csv
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from demand_ingestion.config import Settings, get_settings


class RegionMasterError(ValueError):
    """Raised when a configured region master cannot be used."""


class RegionMasterEntry(BaseModel):
    """A region and its configured geographic coordinates."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    region_id: str = Field(min_length=1, max_length=100)
    region_name: str | None = Field(default=None, max_length=255)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


def load_region_master(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> list[RegionMasterEntry]:
    """Load configured region coordinates from a CSV/CSV-formatted TXT file."""

    config = settings or get_settings()
    dataset_path = Path(path or config.region_master_dataset_path)
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Region master dataset not found: {dataset_path}"
        )

    regions: list[RegionMasterEntry] = []
    seen_ids: set[str] = set()
    try:
        with dataset_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise RegionMasterError("Region master is empty.")

            id_column = (
                "region_id"
                if "region_id" in reader.fieldnames
                else "location_id"
                if "location_id" in reader.fieldnames
                else None
            )
            if id_column is None or not {
                "latitude",
                "longitude",
            }.issubset(reader.fieldnames):
                raise RegionMasterError(
                    "Region master requires region_id (or location_id), "
                    "latitude, and longitude columns."
                )

            for line_number, row in enumerate(reader, start=2):
                region_id = (row.get(id_column) or "").strip()
                if region_id in seen_ids:
                    raise RegionMasterError(
                        f"Duplicate region_id {region_id!r} at line {line_number}."
                    )

                try:
                    entry = RegionMasterEntry(
                        region_id=region_id,
                        region_name=(
                            row.get("region_name")
                            or row.get("region_of_kolkata")
                            or None
                        ),
                        latitude=row.get("latitude"),
                        longitude=row.get("longitude"),
                    )
                except ValidationError as exc:
                    raise RegionMasterError(
                        f"Invalid region master record at line {line_number}."
                    ) from exc

                seen_ids.add(region_id)
                regions.append(entry)
    except UnicodeDecodeError as exc:
        raise RegionMasterError(
            "Region master must be a UTF-8 CSV file."
        ) from exc

    if not regions:
        raise RegionMasterError("Region master contains no region records.")
    return regions
