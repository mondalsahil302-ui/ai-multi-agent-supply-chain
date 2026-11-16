"""Live traffic test suite for FastAPI service (port 8000) and Streamlit dashboard (port 8501)."""
import json
import time
import requests

BASE_API = "http://127.0.0.1:8000"
BASE_STREAMLIT = "http://127.0.0.1:8501"
API_KEY = "demand-agent-secret-key-2026"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

REPORT = []


def record_test(name: str, passed: bool, status_code: int, latency_ms: float, detail: str):
    REPORT.append({
        "name": name,
        "passed": passed,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 2),
        "detail": detail,
    })
    symbol = "✓ PASS" if passed else "✗ FAIL"
    print(f"{symbol} [{latency_ms:.1f}ms] {name} (HTTP {status_code}) -> {detail[:100]}")


def run_live_traffic_suite():
    print("=" * 70)
    print("DEMAND AGENT LIVE TRAFFIC & END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Health check (unauthenticated)
    t0 = time.time()
    r = requests.get(f"{BASE_API}/health")
    lat = (time.time() - t0) * 1000
    record_test(
        "1. GET /health (Unauthenticated)",
        r.status_code == 200 and r.json().get("status") == "healthy",
        r.status_code,
        lat,
        f"Database: {r.json().get('database')}, Region: {r.json().get('region_id')}",
    )

    # 2. Security Check: Unauthenticated access rejected
    t0 = time.time()
    r = requests.get(f"{BASE_API}/readiness/check")
    lat = (time.time() - t0) * 1000
    record_test(
        "2. GET /readiness/check (No Auth Header -> 401)",
        r.status_code == 401,
        r.status_code,
        lat,
        f"Correctly rejected unauthorized request: {r.json().get('detail')}",
    )

    # 3. Data Readiness Check on Pilot Warehouse (WH-001)
    t0 = time.time()
    r = requests.get(f"{BASE_API}/readiness/check?warehouse_id=WH-001&target_week=W151", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    record_test(
        "3. GET /readiness/check (WH-001 on W151)",
        r.status_code == 200 and body.get("ready") is True,
        r.status_code,
        lat,
        f"Ready: {body.get('ready')}, Issues: {len(body.get('issues', []))}",
    )

    # 4. Data Readiness Check on Unpopulated Warehouse (WH-002 -> 409 Conflict)
    t0 = time.time()
    r = requests.get(f"{BASE_API}/readiness/check?warehouse_id=WH-002&target_week=W151", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    record_test(
        "4. GET /readiness/check (WH-002 Unpopulated -> 409)",
        r.status_code == 409 and body.get("detail", {}).get("ready") is False,
        r.status_code,
        lat,
        f"Gate blocked: {body.get('detail', {}).get('issues', [{}])[0].get('detail', '')}",
    )

    # 5. Trigger Single SKU Forecast (ICE-001 on WH-001)
    t0 = time.time()
    payload = {"warehouse_id": "WH-001", "product_id": "ICE-001", "target_week": "W151"}
    r = requests.post(f"{BASE_API}/forecast/run", headers=HEADERS, json=payload)
    lat = (time.time() - t0) * 1000
    body = r.json()
    run_id = body.get("run_id")
    task_out = body.get("tasks", [{}])[0] if body.get("tasks") else {}
    record_test(
        "5. POST /forecast/run (ICE-001 single SKU)",
        r.status_code == 200 and body.get("status") == "SUCCESS",
        r.status_code,
        lat,
        f"Run ID: {run_id}, Forecast: {task_out.get('point_forecast')} units, Method: {task_out.get('method')}",
    )

    # 6. Trigger Forecast on Unpopulated Warehouse (WH-002 -> 409 Refusal)
    t0 = time.time()
    payload_bad = {"warehouse_id": "WH-002", "target_week": "W151"}
    r = requests.post(f"{BASE_API}/forecast/run", headers=HEADERS, json=payload_bad)
    lat = (time.time() - t0) * 1000
    record_test(
        "6. POST /forecast/run (WH-002 Gate Refusal -> 409)",
        r.status_code == 409,
        r.status_code,
        lat,
        f"Correctly refused unpopulated warehouse: status={r.json().get('detail', {}).get('status')}",
    )

    # 7. Query Run Status by Run ID
    t0 = time.time()
    r = requests.get(f"{BASE_API}/forecast/status/{run_id}", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    record_test(
        "7. GET /forecast/status/{run_id}",
        r.status_code == 200 and body.get("found") is True,
        r.status_code,
        lat,
        f"Found: {body.get('found')}, Status: {body.get('metadata', {}).get('status')}",
    )

    # 8. Query Forecast Results Filtered by Warehouse & Week
    t0 = time.time()
    r = requests.get(f"{BASE_API}/forecast/results?warehouse_id=WH-001&target_week=W151&limit=5", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    record_test(
        "8. GET /forecast/results (Filter WH-001, W151)",
        r.status_code == 200 and body.get("count", 0) >= 1,
        r.status_code,
        lat,
        f"Retrieved {body.get('count')} records, Top product: {body.get('results', [{}])[0].get('product_id')}",
    )

    # 9. Get Mathematical SHAP Explanation for ICE-001
    t0 = time.time()
    r = requests.get(f"{BASE_API}/explain/ICE-001?warehouse_id=WH-001&target_week=W151", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    drivers = body.get("top_drivers", [])
    record_test(
        "9. GET /explain/ICE-001 (Linear SHAP Drivers)",
        r.status_code == 200 and len(drivers) > 0,
        r.status_code,
        lat,
        f"Status: {body.get('status')}, Drivers count: {len(drivers)}, Top driver: {drivers[0].get('feature')} (SHAP: {drivers[0].get('shap_value')})",
    )

    # 10. Get System & Warehouse Diagnostic Summary
    t0 = time.time()
    r = requests.get(f"{BASE_API}/data/summary?warehouse_id=WH-001", headers=HEADERS)
    lat = (time.time() - t0) * 1000
    body = r.json()
    record_test(
        "10. GET /data/summary (WH-001 Diagnostics)",
        r.status_code == 200 and "historical_demand" in body,
        r.status_code,
        lat,
        f"Demand records: {body.get('historical_demand', {}).get('records')}, Approved champions: {body.get('model_registry', {}).get('approved_champions')}",
    )

    # 11. Streamlit Dashboard HTTP & Health Response
    t0 = time.time()
    r = requests.get(f"{BASE_STREAMLIT}/")
    r_health = requests.get(f"{BASE_STREAMLIT}/_stcore/health")
    lat = (time.time() - t0) * 1000
    is_ok = (r.status_code == 200 and r_health.status_code == 200 and r_health.text.strip() == "ok")
    record_test(
        "11. GET http://127.0.0.1:8501/ (Streamlit Dashboard & Health)",
        is_ok,
        r.status_code,
        lat,
        f"Streamlit frontend responsive, health check: '{r_health.text.strip()}', HTML size: {len(r.text)} bytes",
    )

    print("=" * 70)
    passed_count = sum(1 for t in REPORT if t["passed"])
    print(f"SUMMARY: {passed_count}/{len(REPORT)} Live Traffic Tests Passed!")
    print("=" * 70)

    # Print top drivers breakdown
    if drivers:
        print("\nTOP MATHEMATICAL SHAP DRIVERS FOR ICE-001:")
        for idx, d in enumerate(drivers, 1):
            sign = "+" if d["shap_value"] > 0 else ""
            print(f"  {idx}. {d['description']:<45} | SHAP: {sign}{d['shap_value']:.4f} | Observed: {d['feature_value']}")


if __name__ == "__main__":
    run_live_traffic_suite()
