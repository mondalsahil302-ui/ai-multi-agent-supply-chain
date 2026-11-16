import logging
from pymongo import MongoClient
from pymongo.database import Database
from demand_agent.config import Settings

log = logging.getLogger(__name__)


def get_db(settings: Settings) -> Database:
    client = MongoClient(
        settings.mongo_uri,
        username=settings.mongo_username,
        password=settings.mongo_password,
        authSource=settings.mongo_auth_source,
        serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
        connectTimeoutMS=settings.mongo_connect_timeout_ms,
        socketTimeoutMS=settings.mongo_socket_timeout_ms,
    )
    client.admin.command("ping")
    db = client[settings.mongo_database]
    db[settings.collections["calendar_weeks"]].find_one({}, {"_id": 1})  # forces an authenticated call
    return db