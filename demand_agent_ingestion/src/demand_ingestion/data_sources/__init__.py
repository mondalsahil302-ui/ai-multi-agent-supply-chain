"""Region-coordinate support for external API ingestion."""

from demand_ingestion.data_sources.region_master import (
    RegionMasterEntry,
    load_region_master,
)

__all__ = ["RegionMasterEntry", "load_region_master"]
