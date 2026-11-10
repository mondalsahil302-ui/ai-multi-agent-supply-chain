"""Independent historical-demand dataset discovery and MongoDB loading."""

from demand_ingestion.historical_demand.dataset_discovery import (
    DatasetDescriptor,
    DatasetDiscoveryError,
    discover_dataset,
)
from demand_ingestion.historical_demand.schema_profile import (
    HistoricalDemandProfile,
    profile_dataset,
)

__all__ = [
    "DatasetDescriptor",
    "DatasetDiscoveryError",
    "HistoricalDemandProfile",
    "discover_dataset",
    "profile_dataset",
]
