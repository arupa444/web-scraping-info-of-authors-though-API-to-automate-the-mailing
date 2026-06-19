@echo off
rem iceReach control script (Windows).
rem
rem   run.bat full        Start API + SPA + background worker
rem   run.bat api         Start only the API/SPA server
rem   run.bat worker      Start only the background worker
rem   run.bat status      Show what's running + a /health check
rem   run.bat logs [worker]   Tail logs (API by default; "logs worker" for the worker)
rem   run.bat stop        Stop everything this script started
rem   run.bat restart     Stop, then start full
rem   run.bat build       Build the React SPA (frontend\dist)
rem   run.bat migrate     Apply DB migrations (alembic upgrade head)
rem   run.bat open        Open the app in your browser
rem   run.bat help        This help
rem
rem Leading dashes are accepted too:  run.bat --full  ==  run.bat full
rem Override the port:  set PORT=9000 && run.bat full
setlocal enableextensions
cd /d "%~dp0"

if "%PORT%"=="" set "PORT=8000"
set "PY=.venv\Scripts\python.exe"
set "RUN=.run"
set "URL=http://127.0.0.1:%PORT%/"
if not exist "%RUN%" mkdir "%RUN%"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=help"
set "CMD=%CMD:--=%"

if /i "%CMD%"=="full"    goto :full
if /i "%CMD%"=="api"     goto :api
if /i "%CMD%"=="worker"  goto :worker
if /i "%CMD%"=="status"  goto :status
if /i "%CMD%"=="logs"    goto :logs
if /i "%CMD%"=="stop"    goto :stop
if /i "%CMD%"=="restart" goto :restart
if /i "%CMD%"=="build"   goto :build
if /i "%CMD%"=="migrate" goto :migrate
if /i "%CMD%"=="open"    goto :open
if /i "%CMD%"=="help"    goto :help
echo Unknown command: %CMD%
goto :help

:checkvenv
if not exist "%PY%" (
  echo No .venv found. Run:  uv venv ^&^& .venv\Scripts\activate ^&^& uv pip install -r requirements.txt
  exit /b 1
)
exit /b 0

:startapi
call :checkvenv || exit /b 1
if not exist "frontend\dist\index.html" call :dobuild
start "iceReach-API" /min cmd /c "%PY% -m uvicorn icereach.main:app --app-dir backend --port %PORT% > %RUN%\api.log 2>&1"
echo API + SPA starting on %URL%  (logs: %RUN%\api.log)
exit /b 0

:startworker
call :checkvenv || exit /b 1
start "iceReach-Worker" /min cmd /c "set PYTHONPATH=backend&& %PY% -m icereach.services.queue > %RUN%\worker.log 2>&1"
echo Worker starting  (logs: %RUN%\worker.log)
exit /b 0

:dobuild
pushd frontend && call npm install && call npm run build & popd
exit /b 0

:full
call :startapi
call :startworker
echo Waiting for the API...
for /l %%i in (1,1,30) do (
  curl -fs %URL%health >nul 2>&1 && goto :fullup
  timeout /t 1 >nul
)
:fullup
start "" "%URL%"
echo iceReach is up: %URL%
echo status: run.bat status    logs: run.bat logs    stop: run.bat stop
goto :end

:api
call :startapi
start "" "%URL%"
goto :end

:worker
call :startworker
goto :end

:status
curl -fs %URL%health >nul 2>&1 && (echo API     RUNNING - %URL%) || (echo API     stopped)
tasklist /v /fi "imagename eq cmd.exe" 2>nul | findstr /i "iceReach-Worker" >nul && (echo Worker  RUNNING) || (echo Worker  stopped)
curl -fs %URL%health 2>nul
goto :end

:logs
if /i "%~2"=="worker" (
  powershell -NoProfile -Command "Get-Content '%RUN%\worker.log' -Tail 50 -Wait"
) else (
  powershell -NoProfile -Command "Get-Content '%RUN%\api.log' -Tail 50 -Wait"
)
goto :end

:stop
taskkill /fi "WINDOWTITLE eq iceReach-Worker*" /t /f >nul 2>&1 && echo Stopped worker. || echo Worker not running.
taskkill /fi "WINDOWTITLE eq iceReach-API*" /t /f >nul 2>&1 && echo Stopped API. || echo API not running.
goto :end

:restart
call :stop
timeout /t 1 >nul
goto :full

:build
call :dobuild
goto :end

:migrate
call :checkvenv || goto :end
if "%DATABASE_URL%"=="" set "DATABASE_URL=sqlite:///./icereach.db"
"%PY%" -m alembic -c backend\alembic.ini upgrade head
goto :end

:open
start "" "%URL%"
goto :end

:help
echo.
echo iceReach control script (Windows)
echo   run.bat full ^| api ^| worker ^| status ^| logs [worker] ^| stop ^| restart ^| build ^| migrate ^| open ^| help
echo.
echo Examples:
echo   run.bat full        Start everything (API + SPA + worker)
echo   run.bat status      Is it running? + /health
echo   run.bat logs        Tail the API log (run.bat logs worker for the worker)
echo   run.bat stop        Stop everything
echo.
goto :end

:end
endlocal
