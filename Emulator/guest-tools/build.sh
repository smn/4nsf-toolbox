#!/bin/sh
# Regenerate every guest test program in bin/ (needs: pip install keystone-engine).
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
COM='\My Flash Disk\VwUserShell\VwCommunicationExe.exe|'
BRAND='\My Flash Disk\VwBrandDevice\VwBrandDevice.exe|'
SHELL_='\My Flash Disk\VwUserShell\VwUserShell.exe|-ShowWindow=1'
$PY mklaunch.py bin/launch-all.exe   hidetaskbar "$COM" "$BRAND" "$SHELL_"
$PY mklaunch.py bin/launch-brand.exe hidetaskbar "$BRAND"
$PY mklaunch.py bin/launch-shell.exe hidetaskbar "$SHELL_"
$PY mkloadtest.py bin/loadtest.exe
$PY mkwintest.py bin/wintest.exe
$PY mkstacks.py bin/stacks.exe
$PY mkgditest.py bin/gditest.exe
$PY mktimertest.py bin/timertest7.exe MMTimer.dll
$PY mksock2.py bin/socktest.exe
