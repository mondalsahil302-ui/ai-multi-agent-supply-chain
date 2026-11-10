import logging
from collections.abc import Callable, Iterable
from types import TracebackType
from typing import Any, TypeVar

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.database.indexes import ensure_indexes

logger = logging.getLogger(__name__)
Result = TypeVar("Result")


class MongoDatabase:
    """Own a configured MongoDB client and the ingestion database."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: MongoClient[Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None
        if client is not None:
            self.client = client
        else:
            options: dict[str, Any] = {
                "serverSelectionTimeoutMS": self.settings.mongo_server_selection_timeout_ms,
                "connectTimeoutMS": self.settings.mongo_connect_timeout_ms,
                "socketTimeoutMS": self.settings.mongo_socket_timeout_ms,
                "retryWrites": True,
            }
            if self.settings.mongo_username and self.settings.mongo_username.strip():
                options["username"] = self.settings.mongo_username
                if self.settings.mongo_password is not None:
                    options["password"] = (
                        self.settings.mongo_password.get_secret_value()
                    )
                options["authSource"] = self.settings.mongo_auth_source
            self.client = MongoClient(
                self.settings.mongo_uri.get_secret_value(),
                **options,
            )
        self.database: Database[Any] = self.client[self.settings.mongo_database]

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "MongoDatabase":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def ping(self) -> None:
        self.run_with_retry(lambda: self.client.admin.command("ping"))

    def ensure_schema(
        self,
        collection_names: Iterable[str],
    ) -> None:
        """Ensure selected ingestion indexes without touching unrelated paths."""

        ensure_indexes(self.database, collection_names)

    def run_with_retry(self, operation: Callable[[], Result]) -> Result:
        retryer = Retrying(
            retry=retry_if_exception_type(
                (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError)
            ),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.25, max=2),
            reraise=True,
        )
        try:
            return retryer(operation)
        except (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError):
            logger.error("MongoDB operation failed after bounded retries.")
            raise
