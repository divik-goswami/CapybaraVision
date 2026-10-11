@echo off
setlocal
set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY_EXE%" (
    "%PY_EXE%" "%~dp0settings_app.py" %*
) else (
    python "%~dp0settings_app.py" %*
)
pause
