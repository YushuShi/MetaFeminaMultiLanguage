@echo off
echo Starting MetaFemina Server...
start "" http://localhost:5000
venv\Scripts\python.exe app.py
