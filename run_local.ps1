Write-Host "Starting inso-wallet server..." -ForegroundColor Green
Write-Host ""

# Activate virtual environment
& .\venv\Scripts\Activate.ps1

# Start the server
Write-Host "Starting FastAPI server on http://0.0.0.0:8080" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""
uvicorn main:app --host 0.0.0.0 --port=8080 --reload

