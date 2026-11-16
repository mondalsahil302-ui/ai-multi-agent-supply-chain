@echo off
title Demand Agent - Full Stack Starter
echo ===================================================
echo Launching Demand Agent Services (API + Dashboard)...
echo ===================================================
cd /d D:\ai-multi-agent-supply-chain\demand_agent_project

echo [1/2] Starting FastAPI Backend on Port 8000...
start "Demand Agent Backend (Port 8000)" cmd /k ".\.venv\Scripts\uvicorn.exe demand_agent.api.app:app --host 0.0.0.0 --port 8000"

timeout /t 2 >nul

echo [2/2] Starting Streamlit Dashboard on Port 8501...
start "Demand Agent Dashboard (Port 8501)" cmd /k ".\.venv\Scripts\streamlit.exe run dashboard/app.py --server.port 8501"

echo.
echo ===================================================
echo Services successfully started:
echo   - Frontend UI:  http://localhost:8501
echo   - Backend API:  http://localhost:8000
echo   - API Docs:     http://localhost:8000/docs
echo ===================================================
timeout /t 5 >nul
