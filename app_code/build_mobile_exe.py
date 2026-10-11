"""
mobile_app.py -> JongJongTrader_Mobile.exe 빌드 스크립트
flet pack (PyInstaller 기반) 사용
"""
import os
import sys
import subprocess
import shutil

# UTF-8 출력 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

os.environ["PYTHONIOENCODING"] = "utf-8"

print("=" * 55)
print("  JongJong Trader Mobile -> EXE 빌드 시작")
print("=" * 55)

current_dir = os.path.dirname(os.path.abspath(__file__))
flet_exe = os.path.join(current_dir, ".venv", "Scripts", "flet.exe")
target_script = os.path.join(current_dir, "mobile_app.py")

if not os.path.exists(flet_exe):
    print(f"[오류] flet.exe 를 찾을 수 없습니다: {flet_exe}")
    sys.exit(1)

if not os.path.exists(target_script):
    print(f"[오류] mobile_app.py 를 찾을 수 없습니다: {target_script}")
    sys.exit(1)

print(f"  flet    : {flet_exe}")
print(f"  소스    : {target_script}")
print("  출력    : dist/JongJongTrader_Mobile.exe")
print("-" * 55)

temp_dist = os.path.join(current_dir, "build", "dist_mobile")
final_dist = os.path.join(current_dir, "dist")
os.makedirs(final_dist, exist_ok=True)

from core.app_update import APP_VERSION

# flet pack 명령 실행
cmd = [
    flet_exe,
    "pack",
    "-y",
    "--distpath", temp_dist,
    "--name", "JongJongTrader_Mobile",
    "--product-name", "JongJong Trader",
    "--product-version", APP_VERSION,
    "--file-version", f"{APP_VERSION}.0",
    target_script,
    "--",
    "--noconsole",
    "--clean",
    "--noconfirm",
    "--hidden-import=flet",
    "--hidden-import=flet_core",
    "--hidden-import=pandas",
    "--hidden-import=numpy",
    "--hidden-import=yfinance",
    "--hidden-import=requests",
    "--hidden-import=urllib3",
    "--hidden-import=certifi",
    "--hidden-import=charset_normalizer",
    "--hidden-import=mobile",
    "--hidden-import=mobile.theme",
    "--hidden-import=mobile.helpers",
    "--hidden-import=mobile.widgets",
    "--hidden-import=mobile.charts",
    "--hidden-import=mobile.views",
    "--hidden-import=mobile.views.home",
    "--hidden-import=mobile.views.accounts",
    "--hidden-import=mobile.views.account_detail",
    "--hidden-import=mobile.views.backtest",
    "--hidden-import=mobile.views.strategies",
    "--hidden-import=mobile.views.settings",
    "--hidden-import=mobile.views.dialogs",
    "--hidden-import=core.strategy_registry",
    "--hidden-import=core.backtest_runner",
    "--hidden-import=core.trade_history",
    "--hidden-import=core.app_settings",
    "--hidden-import=core.account_manager",
    "--hidden-import=core.order_netting",
    "--hidden-import=gui.account_manager",
    "--hidden-import=gui.order_netting",
]

print("실행 중... (수 분 소요될 수 있습니다)")
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

res = subprocess.run(cmd, env=env, cwd=current_dir)

if res.returncode == 0:
    print("\n" + "=" * 55)
    print("  빌드 성공!")
    print("=" * 55)
    built_exe = os.path.join(temp_dist, "JongJongTrader_Mobile.exe")
    final_exe = os.path.join(final_dist, "JongJongTrader_Mobile.exe")
    if os.path.exists(built_exe):
        shutil.copy2(built_exe, final_exe)
        size_mb = os.path.getsize(final_exe) / (1024 * 1024)
        print(f"  EXE 경로 : {final_exe}")
        print(f"  크기     : {size_mb:.1f} MB")
    else:
        print(f"  [경고] {built_exe}를 찾지 못했습니다.")
else:
    print(f"\n[빌드 실패] 종료 코드: {res.returncode}")
    sys.exit(res.returncode)
