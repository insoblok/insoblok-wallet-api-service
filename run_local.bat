@echo off
echo Starting inso-wallet server...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the server
echo Starting FastAPI server on http://0.0.0.0:8080
echo Press Ctrl+C to stop the server
echo.
uvicorn main:app --host 0.0.0.0 --port=8080 --reload

