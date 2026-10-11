"""
Python 소스코드를 Android Flet APK 빌드 프로젝트(flet_apk_project)로 동기화하는 스크립트
"""
import os
import shutil
import glob

BASE_DIR = r"C:\ai_development"
SRC_APP = os.path.join(BASE_DIR, "mobile_app.py")

FLET_PROJECT = os.path.join(BASE_DIR, "flet_apk_project")
FLET_PYTHON_APP = os.path.join(FLET_PROJECT, "build", "python-app")

print("=== Syncing Python app for Mobile / Android APK ===")

# 1. 대상 디렉터리의 이전 .pyc 바이트코드 및 __pycache__ 정리
if os.path.exists(FLET_PYTHON_APP):
    print(f"Cleaning bytecode from {FLET_PYTHON_APP}...")
    for root, dirs, files in os.walk(FLET_PYTHON_APP, topdown=False):
        for f in files:
            if f.endswith(('.pyc', '.pyo')):
                pyc_path = os.path.join(root, f)
                try:
                    os.remove(pyc_path)
                except Exception as e:
                    print(f"  Warning removing {pyc_path}: {e}")
        for d in dirs:
            if d == '__pycache__':
                pycache_path = os.path.join(root, d)
                try:
                    shutil.rmtree(pycache_path)
                except Exception as e:
                    print(f"  Warning removing {pycache_path}: {e}")

# 2. 메인 애플리케이션 파일 동기화
target_mains = [
    os.path.join(FLET_PROJECT, "main.py"),
    os.path.join(FLET_PYTHON_APP, "main.py"),
]

for tm in target_mains:
    os.makedirs(os.path.dirname(tm), exist_ok=True)
    shutil.copy2(SRC_APP, tm)
    print(f"Copied {SRC_APP} -> {tm}")

# 3. 핵심 파이썬 모듈 (core, gui, strategies, mobile) 동기화
for folder in ["core", "gui", "strategies", "mobile"]:
    src_folder = os.path.join(BASE_DIR, folder)
    if not os.path.exists(src_folder):
        continue

    dest_dirs = [
        os.path.join(FLET_PROJECT, folder),
        os.path.join(FLET_PYTHON_APP, folder)
    ]

    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)

    for root, dirs, files in os.walk(src_folder):
        rel_dir = os.path.relpath(root, src_folder)
        for f in files:
            if f.endswith(".py"):
                s_item = os.path.join(root, f)
                for d in dest_dirs:
                    target_dir = d if rel_dir == "." else os.path.join(d, rel_dir)
                    os.makedirs(target_dir, exist_ok=True)
                    dest_file = os.path.join(target_dir, f)
                    shutil.copy2(s_item, dest_file)
                display_path = f"{folder}/{f}" if rel_dir == "." else f"{folder}/{rel_dir}/{f}"
                print(f"   Synced {display_path} (Pure Python source)")

# 4. 데이터 파일 동기화
data_src = os.path.join(BASE_DIR, "data")
if os.path.exists(data_src):
    d_target = os.path.join(FLET_PYTHON_APP, "data")
    if os.path.exists(os.path.dirname(d_target)):
        os.makedirs(d_target, exist_ok=True)
        # 주의: 개인 계좌 데이터(accounts.json)는 공개 배포 APK에 절대 포함하지 않음
        stale = os.path.join(d_target, "accounts.json")
        if os.path.exists(stale):
            os.remove(stale)
            print("   Removed bundled data/accounts.json (privacy)")
        for f in ["accounts.example.json", "market_data.db"]:
            sf = os.path.join(data_src, f)
            if os.path.exists(sf):
                shutil.copy2(sf, os.path.join(d_target, f))
                print(f"   Synced data/{f}")

# 5. 캐시된 gradle 중간 에셋 및 app.zip 삭제 (클린 빌드 유도)
flutter_build = os.path.join(FLET_PROJECT, "build", "flutter", "build")
if os.path.exists(flutter_build):
    for sub in [
        os.path.join(flutter_build, "app", "intermediates", "assets"),
        os.path.join(flutter_build, "app", "intermediates", "compressed_assets"),
        os.path.join(flutter_build, "serious_python_android", "intermediates"),
    ]:
        if os.path.exists(sub):
            print(f"Removing intermediate cache: {sub}")
            try:
                shutil.rmtree(sub)
            except Exception as e:
                print(f"Warning removing {sub}: {e}")

    for zip_file in glob.glob(os.path.join(flutter_build, "**", "app.zip"), recursive=True):
        print(f"Removing cached app.zip: {zip_file}")
        try:
            os.remove(zip_file)
        except Exception as e:
            print(f"Warning removing {zip_file}: {e}")

print("Python sync completed successfully! (No host .pyc bytecode packaged)")
