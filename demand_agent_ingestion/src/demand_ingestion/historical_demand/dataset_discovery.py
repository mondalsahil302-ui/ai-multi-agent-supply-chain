"""Discover supplied historical demand files independently of API sources."""

import csv
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from demand_ingestion.config import Settings, get_settings


class DatasetDiscoveryError(ValueError):
    """Raised when a historical dataset cannot be inspected."""


class DatasetDescriptor(BaseModel):
    """File format and header information for a demand dataset."""

    model_config = ConfigDict(extra="forbid")

    path: str
    file_format: str
    columns: list[str]
    delimiter: str


def discover_dataset(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> DatasetDescriptor:
    """Discover a CSV-formatted dataset without importing or modifying it."""

    config = settings or get_settings()
    dataset_path = Path(path or config.historical_demand_dataset_path)
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Historical demand dataset not found: {dataset_path}"
        )

    try:
        with dataset_path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(8192)
            if not sample.strip():
                return DatasetDescriptor(
                    path=str(dataset_path),
                    file_format=_file_format(dataset_path),
                    columns=[],
                    delimiter=",",
                )
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel
            stream.seek(0)
            reader = csv.reader(stream, dialect)
            columns = next(reader, [])
    except UnicodeDecodeError as exc:
        raise DatasetDiscoveryError(
            "Historical demand dataset must be UTF-8 encoded."
        ) from exc
    except csv.Error as exc:
        raise DatasetDiscoveryError(
            "Historical demand dataset has an invalid delimited-text header."
        ) from exc

    return DatasetDescriptor(
        path=str(dataset_path),
        file_format=_file_format(dataset_path),
        columns=[column.strip() for column in columns],
        delimiter=dialect.delimiter,
    )


def _file_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".tsv"}:
        return "delimited_text"
    return suffix.lstrip(".") or "unknown"
