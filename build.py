"""
PyInstaller 打包脚本 — 将0731本地生活圈打包为单文件EXE
运行: python build.py
"""

import PyInstaller.__main__
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

PyInstaller.__main__.run([
    str(BASE_DIR / "main.py"),
    "--name=0731本地生活圈",
    "--onefile",
    "--windowed",
    "--add-data", f"{BASE_DIR / 'templates'};templates",
    "--add-data", f"{BASE_DIR / 'static'};static",
    "--add-data", f"{BASE_DIR / 'models.py'};.",
    "--add-data", f"{BASE_DIR / 'database.py'};.",
    "--hidden-import", "sqlalchemy.ext.declarative",
    "--hidden-import", "jinja2.ext",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--clean",
    "--noconsole",
])

print("\n✅ 打包完成！EXE位于 dist/ 目录下")
