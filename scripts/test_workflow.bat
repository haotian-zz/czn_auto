@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=python"
set "TARGET_TITLE=Chaos Zero Nightmare"
set "PROBE_X=2000"
set "PROBE_Y=1000"

echo CZN Auto test workflow
echo Working directory: %CD%
echo.

echo [1/8] Syntax check
%PYTHON% -m py_compile ^
  src\main.py ^
  src\state_check.py ^
  src\diagnose_input.py ^
  src\commands\cli.py ^
  src\commands\state_check.py ^
  src\commands\diagnose_input.py ^
  src\core\settings.py ^
  src\core\models.py ^
  src\vision\detector.py ^
  src\system\io_system.py ^
  src\system\controls.py ^
  src\actions\common.py ^
  src\ui\logging.py ^
  src\state_machines\live\session.py
if errorlevel 1 goto :failed
echo.

echo [2/8] Config JSON check
%PYTHON% -m json.tool config.json >nul
if errorlevel 1 goto :failed
%PYTHON% -m json.tool config.example.json >nul
if errorlevel 1 goto :failed
echo OK
echo.

echo [3/8] Main entry help
%PYTHON% src\main.py --help >nul
if errorlevel 1 goto :failed
echo OK
echo.

echo [4/8] State-check entry help
%PYTHON% src\state_check.py --help >nul
if errorlevel 1 goto :failed
echo OK
echo.

echo [4b/8] Fresh current-screen state check
%PYTHON% src\state_check.py
if errorlevel 1 goto :failed
echo.

echo [5/8] Window/input dry-run diagnosis at %PROBE_X%,%PROBE_Y%
%PYTHON% src\diagnose_input.py --x %PROBE_X% --y %PROBE_Y% --dry-run
if errorlevel 1 goto :failed
echo.

echo [5b/8] Window/input dry-run diagnosis by title "%TARGET_TITLE%"
%PYTHON% src\diagnose_input.py --target-window-title "%TARGET_TITLE%" --x %PROBE_X% --y %PROBE_Y% --dry-run
if errorlevel 1 goto :failed
echo.

echo [6/8] Live recognition only, no clicking
%PYTHON% src\main.py --live --max-seconds 30
if errorlevel 1 goto :failed
echo.

set /p RUN_CLICK_ONE="Run one-click test? This WILL click the game. y=yes, n=no: "
if /i "%RUN_CLICK_ONE%"=="y" (
  echo [7/8] One-click ACT test
  %PYTHON% src\main.py --live --act --max-seconds 8 --max-clicks 1 --input-backend postmessage_activate
  if errorlevel 1 goto :failed
) else (
  echo [7/8] Skipped one-click ACT test
)
echo.

set /p RUN_CLICK_FLOW="Run small-flow test? This WILL click the game up to 10 times. y=yes, n=no: "
if /i "%RUN_CLICK_FLOW%"=="y" (
  echo [8/8] Small-flow ACT test
  %PYTHON% src\main.py --live --act --max-seconds 60 --max-clicks 10 --input-backend postmessage_activate --advance-on-unknown --fast-start-to-team --wide-match-scales
  if errorlevel 1 goto :failed
) else (
  echo [8/8] Skipped small-flow ACT test
)

echo.
echo All selected tests completed.
call :cleanup_generated
exit /b 0

:failed
set "FAILED_CODE=%errorlevel%"
call :cleanup_generated
echo.
echo Test workflow failed. Last command exit code: %FAILED_CODE%
exit /b %FAILED_CODE%

:cleanup_generated
echo.
echo Cleaning generated test files...
for /d /r . %%D in (__pycache__) do (
  if exist "%%D" rmdir /s /q "%%D" 2>nul
)
if exist debug_live\fresh_state.jpg del /q debug_live\fresh_state.jpg 2>nul
if exist debug_live\fresh_state_annotated.jpg del /q debug_live\fresh_state_annotated.jpg 2>nul
if exist STOP del /q STOP 2>nul
echo Cleanup complete.
exit /b 0
