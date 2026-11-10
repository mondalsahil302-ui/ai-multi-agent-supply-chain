import json
import logging

from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.historical_demand.importer import import_historical_demand


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with MongoDatabase() as mongo:
        result = import_historical_demand(mongo)
    print(
        json.dumps(
            {
                "ingestion_run_id": result["run"].ingestion_run_id,
                "status": result["run"].status.value,
                "records_received": result["run"].records_received,
                "records_validated": result["run"].records_validated,
                "records_inserted": result["run"].records_inserted,
                "records_updated": result["run"].records_updated,
                "records_unchanged": result["run"].records_unchanged,
                "records_quarantined": result["run"].records_quarantined,
                "invalid_rows": result["invalid_rows"],
                "duplicate_rows": result["duplicate_rows"],
                "continuity_gaps": result["continuity_gaps"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
