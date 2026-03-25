@echo off
setlocal

REM Qwen profile + tokens
set PGPT_PROFILES=qwen
set DASHSCOPE_API_KEY=<your_dashscope_api_key>
set HF_TOKEN=<your_huggingface_token>

REM Postgres + auth
set PGPT_INDICATOR_STORE=postgres
set PGPT_AUTO_MIGRATE=1
set PGPT_AUTH_SECRET=<your_auth_secret>

REM Run backend
poetry run python -m private_gpt
