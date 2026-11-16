@echo off
title Demand Agent Streamlit Dashboard
cd /d D:\ai-multi-agent-supply-chain\demand_agent_project
echo Starting Streamlit Dashboard on http://localhost:8501 ...
.\.venv\Scripts\streamlit.exe run dashboard/app.py --server.port 8501
pause
