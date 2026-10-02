@echo off
rem Daedalus launcher (Windows). cmd.exe resolves the extensionless path the
rem hooks use to this file via PATHEXT, so one hook command works everywhere.
setlocal

set "DAEDALUS_ROOT=%~dp0.."
set "PYTHONPATH=%DAEDALUS_ROOT%\src;%PYTHONPATH%"

if defined DAEDALUS_PYTHON (
  "%DAEDALUS_PYTHON%" -m daedalus.cli %*
  goto :eof
)

where /q python.exe && (
  python.exe -m daedalus.cli %*
  goto :eof
)

where /q py.exe && (
  py.exe -3 -m daedalus.cli %*
  goto :eof
)

rem No interpreter: exit quietly, so the session behaves as if Daedalus
rem were not installed rather than reporting a hook failure.
exit /b 0
