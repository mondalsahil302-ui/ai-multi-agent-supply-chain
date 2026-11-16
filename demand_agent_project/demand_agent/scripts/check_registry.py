"""Read-only check of the model_registry collection."""
import argparse
import os
from collections import Counter

from demand_agent.config import get_settings
from demand_agent.db import get_db

REQUIRED_ALL = ["_id", "region_id", "product_id", "model_type", "status", "gate", "fallback_chain"]
REQUIRED_APPROVED = ["artifact_file", "artifact_sha256", "version", "best_alpha", "base_list_price",
                     "feature_schema_version", "feature_count"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", type=int, default=200)
    ap.add_argument("--expected-approved", type=int, default=126)
    args = ap.parse_args()

    s = get_settings()
    db = get_db(s)
    col = db[os.environ.get("COL_MODEL_REGISTRY", "model_registry")]
    docs = list(col.find({}))
    status = Counter(d.get("status") for d in docs)
    problems = []

    ids = [d.get("product_id") for d in docs]
    if len(set(ids)) != len(ids):
        problems.append("duplicate product_id records")
    for d in docs:
        miss = [k for k in REQUIRED_ALL if k not in d]
        if d.get("status") == "APPROVED":
            miss += [k for k in REQUIRED_APPROVED if k not in d]
            if d.get("feature_count") != 34:
                miss.append("feature_count!=34")
            if len(str(d.get("artifact_sha256", ""))) != 64:
                miss.append("bad sha256")
            if d.get("gate", {}).get("verdict") != "PASS":
                miss.append("approved but gate verdict not PASS")
        elif d.get("status") == "NOT_APPROVED" and d.get("gate", {}).get("verdict") == "PASS":
            miss.append("not approved but gate verdict PASS")
        if miss:
            problems.append(f"{d.get('_id')}: {miss}")

    approved = [d for d in docs if d.get("status") == "APPROVED"]
    ok = (len(docs) == args.expected and status.get("APPROVED", 0) == args.expected_approved and not problems)
    print(("OK    " if ok else "FAIL  ") + f"{len(docs)} records (expected {args.expected}) | status: {dict(status)} "
          f"(expected APPROVED {args.expected_approved}) | problems: {len(problems)}")
    for p in problems[:10]:
        print("        -", p)
    if approved:
        gaps = sorted(d["gate"]["gap_vs_best_baseline_pts"] for d in approved)
        print(f"      approved gap vs best baseline (pts): min {gaps[0]:.2f} | median {gaps[len(gaps)//2]:.2f} | max {gaps[-1]:.2f}")
    print("      with rejected_candidate:", sum(1 for d in docs if "rejected_candidate" in d),
          "| with previous_version:", sum(1 for d in docs if "previous_version" in d))
