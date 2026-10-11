@echo off
setlocal
set "PYW_EXE=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PYW_EXE%" (
    start "" "%PYW_EXE%" "%~dp0main.py" %*
) else if exist "%PY_EXE%" (
    start "" "%PY_EXE%" "%~dp0main.py" %*
) else (
    where pythonw >nul 2>&1
    if not errorlevel 1 (
        start "" pythonw "%~dp0main.py" %*
    ) else (
        start "" python "%~dp0main.py" %*
    )
)
