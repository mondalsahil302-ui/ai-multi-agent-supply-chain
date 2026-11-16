import argparse
import logging
import os
from collections import Counter
from pathlib import Path

from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.training.gate import thresholds_from_env
from demand_agent.training.registry import build_candidates, register, verify_registry

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="evaluate the gate, write nothing to MongoDB")
    args = ap.parse_args()

    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    env = os.environ.get
    t = thresholds_from_env(env)
    model_root = Path(env("MODEL_ARTIFACT_DIR", "./artifacts/models"))
    collection = env("COL_MODEL_REGISTRY", "model_registry")

    print(f"Gate rule {t.rule}: WAPE <= {t.max_wape_pct:.0f}% | |bias| <= {t.max_abs_bias_pct:.0f}% | "
          f"<= {t.max_worse_than_baseline_pts:.1f} pt worse than best baseline")
    cands = build_candidates(model_root / "ridge", t)
    approved = [c for c in cands if c["status"] == "APPROVED"]
    print(f"Candidates: {len(cands)} | APPROVED: {len(approved)} | NOT_APPROVED: {len(cands) - len(approved)}")

    reasons = Counter()
    for c in cands:
        for r in c["gate"].get("reasons", []):
            reasons[r.split(" ")[0] if r.startswith(("WAPE", "|bias|")) else "worse than best baseline"] += 1
    print("Fail reasons (a product can have several):", dict(reasons))

    db = get_db(s)
    counts = register(db, collection, cands, dry_run=args.dry_run)
    print(("DRY RUN - nothing written. " if args.dry_run else "Written to MongoDB. ") + f"Actions: {counts}")

    if not args.dry_run:
        v = verify_registry(db, collection, model_root)
        ok = v["total"] == len(cands) and not v["bad"]
        print(("OK    " if ok else "FAIL  ") + f"registry '{collection}': {v['total']} records, "
              f"{v['approved']} approved, {v['not_approved']} not approved, "
              f"{len(v['bad'])} approved records with missing/changed files")
        for name, msg in v["bad"][:10]:
            print(f"        - {name}: {msg}")
        sample_ok = next((d for d in db[collection].find({"status": "APPROVED"}).limit(1)), None)
        sample_no = next((d for d in db[collection].find({"status": "NOT_APPROVED"}).limit(1)), None)
        for label, d in (("Sample APPROVED", sample_ok), ("Sample NOT_APPROVED", sample_no)):
            if d:
                print(f"\n{label}: {d['_id']} | alpha {d.get('best_alpha')} | gate: "
                      f"{d['gate'].get('ridge_wape_pct')}% vs baseline {d['gate'].get('best_baseline_wape_pct')}% "
                      f"| reasons: {d['gate'].get('reasons')}")
