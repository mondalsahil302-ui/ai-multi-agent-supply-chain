"""Non-blocking Explanation Layer (Layer 7).

Provides:
  1. Exact closed-form linear SHAP values for Ridge models:
     phi_i = w_i * (x_i - mu_i) / sigma_i
     Asserts: sum(phi_i) + intercept == y_hat_log
  2. LLM synthesis citing ONLY top SHAP features with strict 10s circuit breaker.
  3. Deterministic rule-based template fallback on any LLM timeout or failure.
  4. Invariant: NEVER fails the forecast because explanation failed.
"""
import concurrent.futures
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from demand_agent.features import FEATURE_COLUMNS

log = logging.getLogger(__name__)

FEATURE_DESCRIPTIONS = {
    "trend_scaled": "Long-term secular sales trend",
    "annual_sin_1": "Primary annual seasonality cycle (sine component)",
    "annual_cos_1": "Primary annual seasonality cycle (cosine component)",
    "annual_sin_2": "Semi-annual seasonality cycle (sine component)",
    "annual_cos_2": "Semi-annual seasonality cycle (cosine component)",
    "season_summer": "Summer seasonal effect",
    "season_monsoon": "Monsoon rainy season effect",
    "season_autumn": "Autumn festival season effect",
    "log_list_price_index": "Price movement relative to baseline list price",
    "discount_fraction": "Promotional discount percentage",
    "promo_flag": "Active marketing promotion",
    "festival_proximity": "Proximity to major regional festival",
    "festival_durga_puja": "Durga Puja festival demand surge",
    "festival_diwali_kali_puja": "Diwali & Kali Puja festival impact",
    "festival_holi": "Holi festival impact",
    "festival_eid_al-fitr": "Eid al-Fitr festival impact",
    "festival_poila_boishakh": "Bengali New Year (Poila Boishakh) impact",
    "festival_christmas": "Christmas holiday impact",
    "temperature_c": "Ambient temperature forecast",
    "rainfall_log1p": "Expected rainfall volume",
    "humidity_pct": "Relative humidity level",
    "heavy_rain_week_50mm": "Severe precipitation warning (>50mm)",
    "lag_1_relative_log": "Immediate prior week sales momentum (Lag 1)",
    "lag_2_relative_log": "Two-week prior sales momentum (Lag 2)",
    "lag_4_relative_log": "Four-week prior sales momentum (Lag 4)",
    "lag_8_relative_log": "Eight-week prior sales momentum (Lag 8)",
    "lag_52_relative_log": "Same-week last year seasonal demand (Lag 52)",
    "lag_52_available": "Availability flag for 52-week historical lag",
    "rolling_4_relative_log": "4-week short-term moving average demand momentum",
    "rolling_8_relative_log": "8-week medium-term moving average demand momentum",
    "stockout_rate_previous_4w": "Recent 4-week stockout frequency",
    "stockout_rate_previous_8w": "Recent 8-week stockout frequency",
    "promo_previous_week": "Promotion activity in preceding week",
    "demand_level_log1p": "Baseline product sales velocity (median demand level)",
}


def compute_linear_shap(ridge_pipeline, feature_row: pd.DataFrame) -> Tuple[Dict[str, float], float, float]:
    """Computes exact closed-form linear SHAP contributions for a StandardScaler + Ridge pipeline.

    Formula: phi_i = w_i * ((x_i - mu_i) / sigma_i)
    Additive Property: sum(phi_i) + intercept == predicted_log_units
    """
    scaler = ridge_pipeline.named_steps["scaler"]
    ridge = ridge_pipeline.named_steps["ridge"]

    x = feature_row[FEATURE_COLUMNS].to_numpy(dtype=float)[0]
    mu = scaler.mean_
    sigma = scaler.scale_
    w = ridge.coef_
    intercept = float(ridge.intercept_)

    # Exact closed-form SHAP contribution
    phi = w * ((x - mu) / sigma)
    pred_shap = intercept + float(np.sum(phi))

    # Validate additivity property with strict tolerance
    pipe_pred = float(ridge_pipeline.predict(feature_row[FEATURE_COLUMNS])[0])
    diff = abs(pred_shap - pipe_pred)
    if diff > 1e-6:
        raise ValueError(f"SHAP additivity assertion failed: diff={diff:.8f}")

    shap_dict = {col: float(phi[i]) for i, col in enumerate(FEATURE_COLUMNS)}
    return shap_dict, intercept, pred_shap


def extract_top_drivers(
    shap_dict: Dict[str, float],
    feature_row: pd.DataFrame,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """Extracts top N features by absolute SHAP contribution."""
    sorted_features = sorted(shap_dict.items(), key=lambda item: abs(item[1]), reverse=True)
    drivers = []
    for feat_name, shap_val in sorted_features[:top_n]:
        raw_val = float(feature_row[feat_name].iloc[0]) if feat_name in feature_row.columns else 0.0
        drivers.append({
            "feature": feat_name,
            "description": FEATURE_DESCRIPTIONS.get(feat_name, feat_name),
            "shap_value": round(shap_val, 4),
            "feature_value": round(raw_val, 4),
            "impact": "positive" if shap_val > 0 else "negative",
            "impact_magnitude": abs(round(shap_val, 4)),
        })
    return drivers


def generate_template_explanation(
    product_id: str,
    product_name: str,
    target_week: str,
    point_forecast: float,
    method: str,
    top_drivers: List[Dict[str, Any]]
) -> str:
    """Deterministic, rule-based fallback explanation guaranteed never to fail."""
    if not top_drivers:
        return (
            f"Forecast of {point_forecast:.1f} units for {product_name} ({product_id}) "
            f"for week {target_week} was generated using {method}. "
            f"Demand is projected from trailing seasonal moving baseline."
        )

    pos_drivers = [d for d in top_drivers if d["impact"] == "positive"]
    neg_drivers = [d for d in top_drivers if d["impact"] == "negative"]

    lines = [
        f"Forecast for **{product_name}** (`{product_id}`) for week **{target_week}** is **{point_forecast:.1f} units** (Method: `{method}`).",
        "",
        "**Key Demand Drivers:**"
    ]

    if pos_drivers:
        lines.append("- **Upward Drivers:**")
        for d in pos_drivers[:3]:
            lines.append(f"  * {d['description']} (impact: +{d['shap_value']:.3f}, observed: {d['feature_value']})")

    if neg_drivers:
        lines.append("- **Downward Drivers:**")
        for d in neg_drivers[:3]:
            lines.append(f"  * {d['description']} (impact: {d['shap_value']:.3f}, observed: {d['feature_value']})")

    lines.append("")
    lines.append(
        "Overall expectation reflects calibrated combination of underlying baseline volume and localized seasonal factors."
    )
    return "\n".join(lines)


def _call_gemini_llm(
    product_id: str,
    product_name: str,
    target_week: str,
    point_forecast: float,
    method: str,
    top_drivers: List[Dict[str, Any]]
) -> str:
    """Calls Gemini API with top SHAP drivers ONLY (no raw data dumps)."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY or GOOGLE_API_KEY configured in environment.")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            f"You are a retail supply chain forecasting analyst for a Kolkata distribution center.\n"
            f"Synthesize an executive demand explanation for:\n"
            f"- Product: {product_name} ({product_id})\n"
            f"- Target Week: {target_week}\n"
            f"- Projected Demand: {point_forecast:.1f} units (Method: {method})\n"
            f"- Top Mathematical Feature Drivers (SHAP contributions):\n"
            f"{json.dumps(top_drivers, indent=2)}\n\n"
            f"Rules:\n"
            f"1. Explain why demand is at this level citing ONLY the top mathematical drivers above.\n"
            f"2. Keep it concise (2-3 short bullet points max, under 100 words).\n"
            f"3. Do not invent unmentioned drivers or raw data.\n"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()
        if not text:
            raise ValueError("Empty response from LLM")
        return text
    except Exception as e:
        log.warning("Gemini LLM call failed: %s", e)
        raise


def explain_forecast(
    product_id: str,
    product_name: str,
    target_week: str,
    point_forecast: float,
    method: str,
    top_drivers: List[Dict[str, Any]],
    timeout_sec: float = 10.0
) -> Dict[str, Any]:
    """Generates explanation with non-blocking circuit breaker fallback.

    Always returns:
      {
         "status": "llm" | "template",
         "explanation_text": str,
         "top_drivers": list,
         "method": method
      }
    """
    # If no drivers or method is baseline/fallback, return clear template explanation
    if not top_drivers or method != "champion":
        text = generate_template_explanation(
            product_id, product_name, target_week, point_forecast, method, top_drivers
        )
        return {
            "status": "template",
            "explanation_text": text,
            "top_drivers": top_drivers,
            "method": method,
        }

    # Attempt LLM with circuit breaker timeout
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _call_gemini_llm,
                product_id, product_name, target_week, point_forecast, method, top_drivers
            )
            text = future.result(timeout=timeout_sec)
            return {
                "status": "llm",
                "explanation_text": text,
                "top_drivers": top_drivers,
                "method": method,
            }
    except Exception as e:
        log.info("LLM explanation timed out or failed (%s); falling back to deterministic template.", e)
        text = generate_template_explanation(
            product_id, product_name, target_week, point_forecast, method, top_drivers
        )
        return {
            "status": "template",
            "explanation_text": text,
            "top_drivers": top_drivers,
            "method": method,
            "fallback_note": f"Template fallback invoked: {type(e).__name__}",
        }
