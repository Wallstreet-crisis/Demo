$env:DEEPSEEK_API_KEY = $env:DEEPSEEK_API_KEY
$env:OPENROUTER_PROVIDER = "deepseek"
$env:OPENROUTER_MODEL = "deepseek-chat"
$env:PYTHONPATH = "D:\project\Demo\backend\src"
$env:IF_HOSTING_LLM_COOLDOWN_SECONDS = "10"
$env:IF_HOSTING_MAX_SKILLS_PER_TICK = "3"
$env:IF_SCHEDULER_VERBOSE = "1"

Set-Location "D:\project\Demo\backend"
$logFile = "D:\project\Demo\backend\server_output.log"
python -c "import uvicorn; uvicorn.run('ifrontier.app.main:create_app', host='0.0.0.0', port=8010, factory=True, reload=False)" *>&1 | Out-File -FilePath $logFile -Encoding utf8
