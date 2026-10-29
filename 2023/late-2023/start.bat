@echo off

set venv=PrayAI

call %USERPROFILE%\Anaconda3\Scripts\activate %USERPROFILE%\Anaconda3
call activate %venv%

cd %~dp0

call python app.py

PAUSE