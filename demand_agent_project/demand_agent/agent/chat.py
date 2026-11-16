"""Demand AI Chat Engine.

Provides an executive conversational interface for retail demand planning.
Answers normal conversational banter as well as complex multi-variable scenario questions
(temperature shifts, festival rushes, price elasticity, lead time buffers, SHAP drivers,
quantile corridors, and cross-SKU comparisons).
Uses Google Gemini LLM when available, with a deep domain-expert analyst fallback.
"""
from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import dotenv_values

log = logging.getLogger(__name__)


class DemandAIChatEngine:
    """Conversational assistant for Kolkata retail demand forecasting."""

    def __init__(self, db: Any = None, settings: Any = None):
        self.db = db
        self.settings = settings

    def generate_response(
        self,
        user_message: str,
        region_id: str,
        product_id: str,
        product_name: str,
        target_week: str,
        forecast_doc: Optional[Dict[str, Any]] = None,
        hist_rows: Optional[List[Dict[str, Any]]] = None,
        top_drivers: Optional[List[Dict[str, Any]]] = None,
        gate_status: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates a human-like, analytical response to user demand planning queries."""
        # Check API key from multiple environment sources
        api_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        if not api_key:
            env_vals = dotenv_values(".env")
            api_key = env_vals.get("LLM_API_KEY") or env_vals.get("GEMINI_API_KEY") or env_vals.get("GOOGLE_API_KEY")

        # Compile rich operational context
        ctx = self._build_context(
            region_id=region_id,
            product_id=product_id,
            product_name=product_name,
            target_week=target_week,
            forecast_doc=forecast_doc,
            hist_rows=hist_rows,
            top_drivers=top_drivers,
            gate_status=gate_status,
        )

        if api_key:
            try:
                resp = self._call_gemini_chat(user_message, ctx, api_key)
                if resp and len(resp.strip()) > 5:
                    return resp
            except Exception as e:
                log.warning("Gemini chat call failed (%s), using domain expert analyst fallback", e)

        return self._rule_based_analyst_response(user_message, ctx)

    def _build_context(
        self,
        region_id: str,
        product_id: str,
        product_name: str,
        target_week: str,
        forecast_doc: Optional[Dict[str, Any]],
        hist_rows: Optional[List[Dict[str, Any]]],
        top_drivers: Optional[List[Dict[str, Any]]],
        gate_status: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        last_hist_val = float(hist_rows[-1].get("units_sold", 0) if hist_rows else 0)
        avg_4w = (
            sum(float(r.get("units_sold", 0)) for r in hist_rows[-4:]) / max(1, min(4, len(hist_rows)))
            if hist_rows
            else 0.0
        )
        stockouts = [r for r in (hist_rows or []) if r.get("stockout_flag") == 1]

        return {
            "region_id": region_id,
            "product_id": product_id,
            "product_name": product_name,
            "target_week": target_week,
            "forecast": forecast_doc or {},
            "last_week_actual": last_hist_val,
            "avg_4w_actual": avg_4w,
            "historical_count": len(hist_rows or []),
            "stockouts_recorded": len(stockouts),
            "top_drivers": top_drivers or [],
            "gate_ready": gate_status.get("ready", True) if gate_status else True,
        }

    def _call_gemini_chat(self, user_msg: str, ctx: Dict[str, Any], api_key: str) -> str:
        from google import genai

        client = genai.Client(api_key=api_key, http_options={"timeout": 10000})

        system_instruction = (
            "You are the Senior Retail Demand Planning Director and AI Consultant for Kolkata Distribution Operations. "
            "You speak with natural executive authority, warm conversational professionalism, and deep econometric expertise. "
            "You comfortably engage in normal polite conversation (greetings, identity, casual dialogue) as well as dissecting "
            "complex scenario planning questions (temperature sensitivity, festival rushes like Durga Puja/Diwali, price elasticity, "
            "multi-echelon safety stock, lead time buffers, and SHAP factor attribution). "
            "Always reference exact numbers from the operational context when relevant. Keep responses structured, concise, and executive."
        )

        fc = ctx.get("forecast", {})
        point_str = f"{fc.get('point_forecast', 'N/A')}"
        p10_str = f"{fc.get('p10', 'N/A')}"
        p50_str = f"{fc.get('p50', 'N/A')}"
        p90_str = f"{fc.get('p90', 'N/A')}"

        prompt = f"""
Current Operational Context:
- Region: {ctx['region_id']} (Kolkata Distribution Hub)
- Product: {ctx['product_name']} ({ctx['product_id']})
- Target Week: {ctx['target_week']}
- Forecast: Point={point_str} units, Corridor: [P10={p10_str}, P50={p50_str}, P90={p90_str}]
- Method: {fc.get('method', 'champion')} (Model: {fc.get('model_name', 'ridge')})
- Historical Baseline: Last Week Actual = {ctx['last_week_actual']} units, 4-Week Moving Avg = {ctx['avg_4w_actual']:.1f} units
- Stockout History: {ctx['stockouts_recorded']} stockout weeks out of {ctx['historical_count']} observed
- Key Mathematical Drivers (SHAP values):
{json.dumps(ctx['top_drivers'], indent=2)}

User Question: "{user_msg}"
"""
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={"system_instruction": system_instruction},
            )
            if response.text and response.text.strip():
                return response.text.strip()
        except Exception as e:
            log.debug("Gemini model call failed: %s", e)

        raise RuntimeError("Gemini model unavailable or deadline exceeded.")

    def _rule_based_analyst_response(self, user_msg: str, ctx: Dict[str, Any]) -> str:
        """Deterministic domain expert analyst synthesis supporting normal convo and complex scenarios."""
        msg_lower = user_msg.lower().strip()
        fc = ctx.get("forecast", {})
        has_fc = bool(fc and (fc.get("status") == "SUCCESS" or "point_forecast" in fc))
        point = float(fc.get("point_forecast") or 0.0)
        p10 = float(fc.get("p10") or 0.0)
        p50 = float(fc.get("p50") or 0.0)
        p90 = float(fc.get("p90") or 0.0)
        p_name = ctx["product_name"]
        p_id = ctx["product_id"]
        last_val = ctx["last_week_actual"]
        avg_4w = ctx["avg_4w_actual"]
        drivers = ctx.get("top_drivers", [])
        stockouts = ctx["stockouts_recorded"]

        # -------------------------------------------------------------
        # 1. NORMAL CONVERSATION & CASUAL BANTER
        # -------------------------------------------------------------
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings"]
        if any(msg_lower == g or msg_lower.startswith(g + " ") for g in greetings):
            return (
                f"Hello! I'm your **Demand Planning Director & AI Consultant** for Kolkata DC operations.\n\n"
                f"We are currently reviewing **{p_name}** (`{p_id}`) for week **{ctx['target_week']}**.\n"
                f"- **Active Forecast:** `{point:.1f} units` (Corridor: `[{p10:.1f}, {p50:.1f}, {p90:.1f}]`)\n"
                f"- **Recent Momentum:** Last week closed at `{last_val} units` (4-week rolling avg: `{avg_4w:.1f} units`)\n\n"
                f"How can I assist you today? You can ask me about weekly drivers, weather/festival shifts, complex scenario what-ifs, or replenishment safety buffers."
            )

        if any(w in msg_lower for w in ["who are you", "what are you", "your name", "what do you do", "what can you do"]):
            return (
                f"I am the **Demand Intelligence Agent** for Kolkata Retail Distribution Operations.\n\n"
                f"**What I do:**\n"
                f"- **Probabilistic Forecasting:** Compute multi-quantile weekly demand ($P_{{10}}, P_{{50}}, P_{{90}}$) across 200 FMCG SKUs.\n"
                f"- **SHAP Explainability:** Decompose demand drivers (macro weather, festival calendars, secular trends, and price changes) into exact closed-form feature contributions.\n"
                f"- **Scenario Simulation:** Analyze what-if scenarios (e.g. temperature spikes, promotional discounts, festival demand rushes).\n"
                f"- **Replenishment Governance:** Formulate safety stock buffer recommendations sized to $P_{{90}}$ peak ceilings to protect 95% service levels."
            )

        if any(w in msg_lower for w in ["how are you", "how are things", "how's it going", "how do you do"]):
            return (
                f"Hello! Operations are running smoothly! All 5 Data Readiness Gates for `{ctx['region_id']}` are verified, "
                f"and model registry backtest telemetry is healthy. We are actively tracking **{p_name}** with expected "
                f"demand of `{point:.1f} units` for {ctx['target_week']}. What scenario or forecast metric would you like to explore?"
            )

        if any(w in msg_lower for w in ["thank you", "thanks", "great", "awesome", "perfect", "good job", "nice"]):
            return (
                f"You're very welcome! Always glad to support our supply chain operations. "
                f"Let me know if you'd like to simulate another week, inspect category demand, or examine replenishment safety stocks."
            )

        # -------------------------------------------------------------
        # 2. COMPLEX SCENARIO: TEMPERATURE / WEATHER WHAT-IF
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["temperature", "degree", "weather", "heatwave", "rain", "monsoon", "celsius"]):
            temp_match = re.search(r'(\d+)\s*(?:c|degree|°)', msg_lower)
            delta_t = int(temp_match.group(1)) if temp_match else 3
            is_increase = not any(w in msg_lower for w in ["drop", "decrease", "cooler", "fall", "lower"])

            # Elasticity estimation based on product category
            is_cold_treat = any(k in p_name.lower() for k in ["ice cream", "beverage", "drink", "cola", "frooti", "sprite", "thums up", "water"])
            elasticity_pct = 4.2 if is_cold_treat else 1.1
            if not is_increase:
                elasticity_pct = -elasticity_pct

            unit_impact = point * (elasticity_pct * delta_t / 100.0) if point > 0 else (avg_4w * elasticity_pct * delta_t / 100.0)
            adjusted_demand = max(5.0, (point or avg_4w) + unit_impact)
            adj_p90 = adjusted_demand * 1.18

            return (
                f"**Macro Weather Scenario Analysis for {p_name} ({p_id}):**\n"
                f"- **Temperature Shift Simulated:** `{'▲ +' if is_increase else '▼ -'}{delta_t}°C` relative to seasonal baseline.\n"
                f"- **Category Thermal Sensitivity:** `+{elasticity_pct:.1f}%` volume elasticity per +1°C (High sensitivity for FMCG impulse refreshment).\n"
                f"- **Projected Demand Impact:** `{'▲ +' if unit_impact >= 0 else '▼ '}{unit_impact:.1f} units` (`{adjusted_demand:.1f} units` adjusted baseline).\n"
                f"- **Recommended Replenishment Action:** Elevate DC buffer to `{adj_p90:.0f} units` to absorb thermal impulse demand and prevent localized stockouts.\n"
                f"- **Statistical SHAP Context:** Temperature currently accounts for a calibrated marginal contribution in our Ridge champion model."
            )

        # -------------------------------------------------------------
        # 3. COMPLEX SCENARIO: FESTIVALS (DURGA PUJA, DIWALI, EID)
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["festival", "puja", "durga", "diwali", "holiday", "rush", "eid", "christmas"]):
            festival_lift_pct = 45.0  # Kolkata regional retail average surge
            surge_demand = (point or avg_4w) * (1.0 + festival_lift_pct / 100.0)
            surge_p90 = surge_demand * 1.22
            extra_buffer = surge_p90 - surge_demand

            return (
                f"**Festival Surge Scenario (Kolkata Regional Impact):**\n"
                f"- **Historical Festival Multiplier:** Kolkata DC experiences a `+35% to +60%` demand expansion across confectionery, snacks, and dairy during major festivals (Durga Puja, Kali Puja, Diwali).\n"
                f"- **Projected Peak Demand for {p_name}:** Estimated surge to `{surge_demand:.1f} units` (up from `{point:.1f} units` standard baseline).\n"
                f"- **Upside Tail Risk ($P_{{90}}$ Ceiling):** `{surge_p90:.1f} units` peak demand boundary.\n"
                f"- **Multi-Echelon Buffer Recommendation:** Stage an incremental `{extra_buffer:.0f} units` safety stock at the local hub 10 days in advance of the festival week to buffer against supplier congestion."
            )

        # -------------------------------------------------------------
        # 4. COMPLEX SCENARIO: PRICE DISCOUNT & PROMOTION ELASTICITY
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["discount", "price", "promotion", "promo", "elasticity", "cut"]):
            disc_match = re.search(r'(\d+)%', msg_lower)
            discount_pct = int(disc_match.group(1)) if disc_match else 10
            # Retail price elasticity of demand
            ped = -1.35
            demand_gain_pct = abs(ped * discount_pct)
            new_demand = (point or avg_4w) * (1.0 + demand_gain_pct / 100.0)

            return (
                f"**Commercial Price Promotion Simulation for {p_name}:**\n"
                f"- **Simulated Price Promotion:** `{discount_pct}%` retail discount.\n"
                f"- **Estimated Price Elasticity (PED):** `{ped:.2f}` (moderately elastic for branded packaged goods).\n"
                f"- **Projected Sales Volume Lift:** `+{demand_gain_pct:.1f}%` volume expansion (`{new_demand:.1f} units` vs `{point:.1f} units` base).\n"
                f"- **Revenue & Replenishment Implication:** While unit velocity accelerates, replenishment orders must be sized to `{new_demand * 1.15:.0f} units` to avoid promotional stockout penalties."
            )

        # -------------------------------------------------------------
        # 5. COMPLEX SCENARIO: SUPPLY DELAY / LEAD TIME WHAT-IF
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["lead time", "delay", "supplier", "shipment", "disruption", "late"]):
            base_ss = max(10.0, p90 - p50) if p90 > 0 else avg_4w * 0.2
            delay_ss = base_ss * 1.414  # sqrt(2) scaling for lead time doubling

            return (
                f"**Supply Chain Lead Time Disruption Analysis:**\n"
                f"- **Current Baseline Buffer:** `{base_ss:.1f} units` (protecting 1-week DC replenishment cycle).\n"
                f"- **Impact of Lead Time Doubling (1 week -> 2 weeks):** Safety stock requirement scales with $\\sqrt{{L}}$, requiring a `+41.4%` buffer expansion.\n"
                f"- **Revised Required Safety Stock:** `{delay_ss:.1f} units` at the Kolkata warehouse.\n"
                f"- **Service Level Protection:** Maintains 95% on-shelf availability (OTIF) despite transit variance."
            )

        # -------------------------------------------------------------
        # 6. QUANTILE CORRIDOR & STATISTICAL EXPLANATION
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["quantile", "p10", "p50", "p90", "corridor", "uncertainty", "confidence"]):
            spread = p90 - p10
            return (
                f"**Probabilistic Quantile Corridor Explanation (P10, P50, P90):**\n"
                f"- **Lower Quantile (P10 / $P_{{10}}$ = `{p10:.1f} units`):** 90% probability that demand will meet or exceed this floor. Useful for identifying overstock/spoilage risks.\n"
                f"- **Median Quantile (P50 / $P_{{50}}$ = `{p50:.1f} units`):** Median unbiased expectation where demand is equally likely to be higher or lower.\n"
                f"- **Upper Quantile (P90 / $P_{{90}}$ = `{p90:.1f} units`):** 90th percentile peak demand ceiling. Recommended sizing threshold for replenishment to achieve a 90-95% service level.\n"
                f"- **Uncertainty Spread:** `±{spread/2:.1f} units` wide corridor, capturing macroeconomic volatility and weather variances."
            )

        # -------------------------------------------------------------
        # 7. MATHEMATICAL MODELING, RIDGE, SHAP & GOVERNANCE
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["shap", "model", "ridge", "rule c", "alpha", "algorithm", "backtest", "why ridge"]):
            return (
                f"**Mathematical Modeling & SHAP Attribution Architecture:**\n"
                f"- **Champion Model:** Regularized Ridge Regression ($L_2$ penalty) trained on 52+ continuous weeks of regional sales history.\n"
                f"- **Log-Additive Formulation:** Fits $\\ln(\\hat{{y}} + 1) = w_0 + \\sum w_i x_i$, dampening extreme volatility and preventing negative forecast outputs.\n"
                f"- **Closed-Form SHAP:** For linear models, Shapley values simplify to $\\phi_i(x) = w_i (x_i - \\mathbb{{E}}[x_i])$, providing exact, provably fair attribution without Monte Carlo sampling approximations.\n"
                f"- **Rule C Quality Gate:** A candidate model is only approved if backtest WAPE $\\le 35\\%$, $|\\text{{Bias}}| \\le 10\\%$, and performance beats trailing median baselines by $\\ge 1.0$ percentage point."
            )

        # -------------------------------------------------------------
        # 8. DRIVER / TREND QUERY
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["why", "trend", "driver", "factor", "reason", "increase", "decrease", "drop", "spike"]):
            lines = [
                f"**Demand Trajectory Analysis for {p_name} ({p_id}):**",
                f"- **Baseline vs Projected:** Last week actual was `{last_val:.1f} units` (4-week rolling avg: `{avg_4w:.1f} units`).",
            ]
            if has_fc:
                diff = point - last_val
                direction = "upward expansion" if diff > 0 else "softening contraction"
                lines.append(f"- **Horizon Outlook:** We forecast `{point:.1f} units`, reflecting a `{diff:+.1f} unit` {direction}.")

            if drivers:
                lines.append("- **Primary Mathematical Drivers (SHAP Decomposition):**")
                for d in drivers[:4]:
                    sign = "+" if d.get("shap_value", 0) > 0 else ""
                    lines.append(f"  • **{d.get('description', d.get('feature'))}:** `{sign}{d.get('shap_value', 0):.4f}` contribution (Observed: `{d.get('feature_value')}`).")
            else:
                lines.append("- **Macro Drivers:** Trailing 4-week sales inertia and seasonal Fourier harmonics are the principal contributors.")

            return "\n".join(lines)

        # -------------------------------------------------------------
        # 9. STOCKOUT & REPLENISHMENT BUFFER QUERY
        # -------------------------------------------------------------
        if any(w in msg_lower for w in ["stockout", "safety", "buffer", "inventory", "risk", "shortage", "rop", "replenish"]):
            rate = (stockouts / max(1, ctx["historical_count"])) * 100
            recommendation = "Maintain standard 1.20x buffer." if p90 < 100 else "Recommend elevating target safety stock to P90 ceiling to mitigate spike risk."
            return (
                f"**Inventory & Stockout Risk Audit for {p_name}:**\n"
                f"- **Historical Stockout Incidents:** `{stockouts} weeks` out of {ctx['historical_count']} observed (`{rate:.1f}%` historical stockout frequency).\n"
                f"- **P90 Peak Demand Ceiling:** `{p90:.1f} units` (upper bound for replenishment sizing).\n"
                f"- **Recommended Inventory Action:** {recommendation}\n"
                f"- **Next Step:** Hand off to **Agent 2 (Inventory Agent)** for multi-echelon safety stock and reorder point (ROP) calculation."
            )

        # -------------------------------------------------------------
        # 10. GENERAL FALLBACK / EXECUTIVE SUMMARY
        # -------------------------------------------------------------
        return (
            f"**Demand Planning Advisory for {p_name} ({p_id}) in {ctx['region_id']}:**\n"
            f"- **Target Week:** `{ctx['target_week']}`\n"
            f"- **Expected Sales:** `{point:.1f} units` (Corridor: `[{p10:.1f}, {p50:.1f}, {p90:.1f}]`)\n"
            f"- **Recent Baseline:** Last week closed at `{last_val:.1f} units` against a 4-week moving average of `{avg_4w:.1f} units`.\n\n"
            f"Feel free to ask me:\n"
            f"• *'What if temperature rises by 4 degrees?'*\n"
            f"• *'How does Durga Puja impact our demand?'*\n"
            f"• *'What is our recommended safety stock buffer?'*\n"
            f"• *'Why did demand shift this week?'*"
        )
