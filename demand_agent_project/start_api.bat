@echo off
title Demand Agent FastAPI Backend
cd /d D:\ai-multi-agent-supply-chain\demand_agent_project
echo Starting FastAPI Backend on http://localhost:8000 ...
.\.venv\Scripts\uvicorn.exe demand_agent.api.app:app --host 0.0.0.0 --port 8000
pause
