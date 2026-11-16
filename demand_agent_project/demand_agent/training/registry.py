"""Per-product model registry in MongoDB (collection: model_registry)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from demand_agent.training.gate import GateThresholds, evaluate_gate

REGISTRY_SCHEMA_VERSION = 1
FALLBACK_CHAIN = ["lightgbm_standby", "rolling_seasonal_baseline"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_candidates(ridge_dir: Path, t: GateThresholds) -> list[dict]:
    """One candidate registry document per <product>.json + <product>.joblib pair."""
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for meta_path in sorted(p for p in ridge_dir.glob("*.json") if not p.name.startswith("_")):
        pid = meta_path.stem
        model_path = ridge_dir / f"{pid}.joblib"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not model_path.exists():
            out.append({"_id": meta.get("series_id", pid), "product_id": pid, "status": "NOT_APPROVED",
                        "gate": {"verdict": "FAIL", "reasons": ["artifact file missing"]},
                        "region_id": meta.get("region_id"), "model_type": "ridge",
                        "registry_schema_version": REGISTRY_SCHEMA_VERSION, "registered_at_utc": now,
                        "fallback_chain": FALLBACK_CHAIN})
            continue
        gate = evaluate_gate(meta.get("metrics", {}), t)
        out.append({
            "_id": meta["series_id"],
            "registry_schema_version": REGISTRY_SCHEMA_VERSION,
            "region_id": meta["region_id"], "product_id": meta["product_id"], "model_type": "ridge",
            "status": "APPROVED" if gate["verdict"] == "PASS" else "NOT_APPROVED",
            "artifact_file": f"ridge/{pid}.joblib",
            "artifact_sha256": sha256_file(model_path),
            "version": meta["trained_at_utc"],
            "trained_at_utc": meta["trained_at_utc"], "training_cutoff": meta["training_cutoff"],
            "training_rows": meta["training_rows"], "best_alpha": meta["best_alpha"],
            "base_list_price": meta["base_list_price"],
            "feature_schema_version": "v1", "feature_count": len(meta["feature_columns"]),
            "gate": gate, "metrics": meta["metrics"],
            "fallback_chain": FALLBACK_CHAIN, "registered_at_utc": now,
        })
    return out


def _pointer(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("version", "artifact_file", "artifact_sha256", "status", "trained_at_utc")}


def register(db, collection: str, candidates: list[dict], dry_run: bool = False) -> dict:
    """Idempotent. A failing candidate never replaces a previously APPROVED champion."""
    col = db[collection]
    counts = {"approved_new": 0, "approved_replaced": 0, "unchanged": 0,
              "kept_previous_champion": 0, "not_approved": 0}
    for cand in candidates:
        existing = col.find_one({"_id": cand["_id"]})
        if cand["status"] == "APPROVED":
            if (existing and existing.get("status") == "APPROVED"
                    and existing.get("artifact_sha256") == cand["artifact_sha256"]):
                counts["unchanged"] += 1
                continue
            if existing:
                cand["previous_version"] = _pointer(existing)
                counts["approved_replaced"] += 1
            else:
                counts["approved_new"] += 1
            if not dry_run:
                col.replace_one({"_id": cand["_id"]}, cand, upsert=True)
        else:
            if existing and existing.get("status") == "APPROVED":
                counts["kept_previous_champion"] += 1
                if not dry_run:
                    col.update_one({"_id": cand["_id"]}, {"$set": {
                        "rejected_candidate": {**_pointer(cand), "gate": cand.get("gate"),
                                               "registered_at_utc": cand["registered_at_utc"]}}})
            else:
                counts["not_approved"] += 1
                if not dry_run:
                    col.replace_one({"_id": cand["_id"]}, cand, upsert=True)
    if not dry_run:
        try:
            col.create_index("status")
        except Exception:                                      # noqa: BLE001 - index is optional
            pass
    return counts


def verify_registry(db, collection: str, model_root: Path) -> dict:
    """Every APPROVED record must point at a file whose checksum still matches."""
    docs = list(db[collection].find({}))
    approved = [d for d in docs if d.get("status") == "APPROVED"]
    bad = []
    for d in approved:
        p = model_root / d["artifact_file"]
        if not p.exists():
            bad.append((d["_id"], "file missing"))
        elif sha256_file(p) != d["artifact_sha256"]:
            bad.append((d["_id"], "checksum mismatch"))
    return {"total": len(docs), "approved": len(approved),
            "not_approved": len(docs) - len(approved), "bad": bad}
