param([int]$Port = 8000)
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
uv run python -m fireatlas.web --judge-demo --host 127.0.0.1 --port $Port
