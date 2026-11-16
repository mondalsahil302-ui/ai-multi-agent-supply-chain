"""Model quality gate (rule C): the Ridge model is approved for a product when
  - test WAPE <= max_wape_pct
  - |test bias| <= max_abs_bias_pct
  - Ridge is NOT more than max_worse_than_baseline_pts percentage points worse than the best baseline
    (best baseline = lower WAPE of trailing-median and 52-week seasonal naive)."""
import math
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class GateThresholds:
    max_wape_pct: float = 35.0
    max_abs_bias_pct: float = 10.0
    max_worse_than_baseline_pts: float = 1.0
    rule: str = "C"


def thresholds_from_env(env) -> GateThresholds:
    return GateThresholds(
        max_wape_pct=float(env("GATE_MAX_WAPE", "0.35")) * 100.0,
        max_abs_bias_pct=float(env("GATE_MAX_ABS_BIAS_PCT", "0.10")) * 100.0,
        max_worse_than_baseline_pts=float(env("GATE_MAX_WORSE_THAN_BASELINE_PTS", "1.0")),
    )


def evaluate_gate(metrics: dict, t: GateThresholds) -> dict:
    try:
        ridge = float(metrics["test_ridge"]["WAPE_pct"])
        bias = float(metrics["test_ridge"]["Bias_pct"])
        median = float(metrics["test_moving_median"]["WAPE_pct"])
        seasonal = float(metrics["test_seasonal_naive"]["WAPE_pct"])
    except (KeyError, TypeError, ValueError):
        return {"verdict": "FAIL", "reasons": ["metrics missing"], "thresholds": asdict(t)}
    if not all(math.isfinite(x) for x in (ridge, bias, median, seasonal)):
        return {"verdict": "FAIL", "reasons": ["non-finite metrics"], "thresholds": asdict(t)}

    best_baseline = min(median, seasonal)
    gap = ridge - best_baseline
    reasons = []
    if ridge > t.max_wape_pct:
        reasons.append(f"WAPE {ridge:.1f}% > {t.max_wape_pct:.0f}%")
    if abs(bias) > t.max_abs_bias_pct:
        reasons.append(f"|bias| {abs(bias):.1f}% > {t.max_abs_bias_pct:.0f}%")
    if gap > t.max_worse_than_baseline_pts:
        reasons.append(f"{gap:.1f} pts worse than best baseline (limit {t.max_worse_than_baseline_pts:.1f})")
    return {
        "verdict": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "ridge_wape_pct": round(ridge, 3), "best_baseline_wape_pct": round(best_baseline, 3),
        "gap_vs_best_baseline_pts": round(gap, 3), "bias_pct": round(bias, 3),
        "thresholds": asdict(t),
    }
