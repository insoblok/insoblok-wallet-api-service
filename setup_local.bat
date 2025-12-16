@echo off
echo Setting up inso-wallet for local development...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Create a .env file in the project root with your configuration
echo 2. Copy the values from app.yaml or use the example below
echo 3. Run: uvicorn main:app --host 0.0.0.0 --port=8080
echo.
echo Example .env file content:
echo INSTANCE_CONNECTION_NAME=your_cloud_sql_instance
echo DB_USER=postgres
echo DB_PASSWORD=your_password
echo DB_NAME=crypto_wallet
echo INFURA_PROJECT_ID=your_infura_project_id
echo ... (see app.yaml for all required variables)
echo.

