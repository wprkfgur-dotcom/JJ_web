#!/usr/bin/env python3
"""
=====================================================================
JJ Invest - Universal Web Server Launcher
Windows & Oracle Cloud Ubuntu Linux Cross-Platform
=====================================================================
"""
import os
import sys
from pathlib import Path

# Windows UTF-8 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 작업 디렉터리 보정
BASE_DIR = Path(__file__).resolve().parent
os.chdir(str(BASE_DIR))

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print("=" * 60)
    print(f"[JJ Invest] Web Server Starting...")
    print(f">> Local URL: http://localhost:{port}")
    print(f">> Binding:   http://{host}:{port}")
    print(f">> Platform:  {sys.platform} (Python {sys.version.split()[0]})")
    print("=" * 60)
    
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,
        workers=1
    )
