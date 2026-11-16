import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


URI = env("MONGO_URI")
USER = env("MONGO_USERNAME")
PWD = env("MONGO_PASSWORD")
DB = env("MONGO_DATABASE")
CONFIGURED_SRC = env("MONGO_AUTH_SOURCE")
TIMEOUT = int(env("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))


def client(auth_source=None):
    kw = dict(serverSelectionTimeoutMS=TIMEOUT)
    if auth_source:
        kw.update(username=USER, password=PWD, authSource=auth_source)
    return MongoClient(URI, **kw)


print(f"URI={URI}  user={USER!r}  password_len={len(PWD)}  db={DB}  configured authSource={CONFIGURED_SRC!r}")
print("-" * 60)

# 1. Server reachable?
try:
    client().admin.command("ping")
    print("OK    server reachable")
except ServerSelectionTimeoutError as e:
    print(f"FAIL  server not reachable: {e}")
    sys.exit(1)

# 2. Is authentication actually enforced? (anonymous read should be refused)
try:
    client()[DB]["region_master"].count_documents({})
    print("WARN  anonymous read worked -> MongoDB auth is NOT enforced")
except OperationFailure as e:
    print(f"OK    anonymous read refused (code {e.code}) -> auth is enforced")

# 3. Try the configured authSource first, then common alternatives
candidates = []
for s in [CONFIGURED_SRC, DB, "admin"]:
    if s and s not in candidates:
        candidates.append(s)

working = None
for src in candidates:
    try:
        c = client(src)
        c.admin.command("ping")
        status = c.admin.command("connectionStatus")["authInfo"]
        users = [f"{u['user']}@{u['db']}" for u in status["authenticatedUsers"]]
        roles = [f"{r['role']}@{r['db']}" for r in status["authenticatedUserRoles"]]
        # connectionStatus is lazy about auth; force a real authenticated call
        c[DB]["region_master"].count_documents({})
        print(f"OK    login works with authSource={src!r}")
        print(f"      user: {users}")
        print(f"      roles: {roles}")
        working = (src, c)
        break
    except OperationFailure as e:
        if e.code == 18:
            print(f"FAIL  authSource={src!r}: AuthenticationFailed (wrong username/password or user not in this db)")
        elif e.code == 13:
            print(f"FAIL  authSource={src!r}: logged in but NOT authorized to read {DB} (missing role)")
        else:
            print(f"FAIL  authSource={src!r}: code {e.code} {e.details.get('errmsg', e)}")

if not working:
    print("-" * 60)
    print("No authSource worked. Check username, password, and which database the user was created in.")
    sys.exit(1)

src, c = working
db = c[DB]

# 4. Read test
n = db["demand_features"].count_documents({})
print(f"OK    read: demand_features has {n} docs")

# 5. Write test (probe collection, then drop)
try:
    db["_auth_probe"].insert_one({"probe": True})
    db["_auth_probe"].drop()
    print("OK    write: insert + drop on a probe collection succeeded")
except OperationFailure as e:
    print(f"FAIL  write: {e.details.get('errmsg', e)} (user is read-only; needs readWrite)")

print("-" * 60)
if src != CONFIGURED_SRC:
    print(f"ACTION: set MONGO_AUTH_SOURCE={src} in .env")
else:
    print("Mongo auth is good. Nothing to change.")