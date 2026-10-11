"""
애플리케이션 버전 관리 및 GitHub Releases 기반 자동 업데이트 모듈
"""
import os
import sys
import re
import json
import email.utils
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

APP_VERSION = "2.4.1"
APP_BUILD_NAME = "JongJong Trader v2.4.1 (Account Detail Latency Optimization)"
# 현재 앱 빌드 기준 타임스탬프 (UTC) 및 한국시간 표시 문자열
APP_BUILD_TIMESTAMP = 1791531900
APP_BUILD_DATE_STR = "2026-10-09 18:05"

DEFAULT_GITHUB_REPO = "wprkfgur-dotcom/jj_invest"
DEFAULT_UPDATE_CHANNEL_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}"
DEFAULT_DIRECT_DOWNLOAD_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}/releases/latest/download/JongJongTrader_ARM64.apk"
DEFAULT_RELEASES_WEB_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}/releases"

# 하위 호환성 별칭
DEFAULT_APK_DRIVE_URL = "https://drive.google.com/file/d/1Dc9OryPfGF8m19XB42JBejXkj8R7AZ_s/view?usp=sharing"

if os.environ.get("FLET_APP_STORAGE_DATA"):
    BASE_DIR = os.environ.get("FLET_APP_STORAGE_DATA")
elif getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
UPDATE_CONFIG_FILE = os.path.join(DATA_DIR, "app_update_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "apk_update_url": DEFAULT_UPDATE_CHANNEL_URL,
    "last_check_time": None,
    "last_check_status": "none",
    "auto_check_on_start": True
}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_update_config() -> Dict[str, Any]:
    """업데이트 설정을 로드합니다."""
    _ensure_dir()
    if not os.path.exists(UPDATE_CONFIG_FILE):
        save_update_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(UPDATE_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 마이그레이션: 기존 구글 드라이브 키가 있으면 변환
            if "apk_drive_url" in cfg and "apk_update_url" not in cfg:
                old_val = cfg.pop("apk_drive_url")
                # 기본 구글 드라이브 링크였던 경우 GitHub 기본 채널로 자동 전환
                if "drive.google.com" in str(old_val):
                    cfg["apk_update_url"] = DEFAULT_UPDATE_CHANNEL_URL
                else:
                    cfg["apk_update_url"] = old_val

            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            if not cfg.get("apk_update_url"):
                cfg["apk_update_url"] = DEFAULT_UPDATE_CHANNEL_URL
            return cfg
    except Exception as e:
        print(f"[AppUpdate] 설정 로드 실패: {e}")
        return dict(DEFAULT_CONFIG)


def save_update_config(config: Dict[str, Any]):
    """업데이트 설정을 저장합니다."""
    _ensure_dir()
    try:
        with open(UPDATE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[AppUpdate] 설정 저장 실패: {e}")


def parse_version_tuple(ver_str: str) -> Tuple[int, ...]:
    """'2.0.1' 등의 버전 문자열을 비교 가능한 튜플 (2, 0, 1)로 변환합니다."""
    if not ver_str:
        return (0, 0, 0)
    nums = [int(n) for n in re.findall(r'\d+', ver_str)]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def extract_github_repo(url: str) -> Optional[Tuple[str, str]]:
    """'https://github.com/owner/repo' 또는 'owner/repo'에서 owner와 repo 추출"""
    if not url:
        return None
    url = url.strip()
    m = re.search(r'github\.com/([^/]+)/([^/#?]+)', url)
    if m:
        return (m.group(1), m.group(2).removesuffix('.git'))
    m = re.search(r'^([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)$', url)
    if m:
        return (m.group(1), m.group(2))
    return None


def extract_gdrive_file_id(url: str) -> Optional[str]:
    """구글 드라이브 공유 링크에서 파일 ID를 추출합니다 (하위 호환)."""
    if not url:
        return None
    url = url.strip()
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    return None


def parse_download_url(url: str) -> str:
    """
    URL을 적절한 직접 다운로드 링크로 변환합니다.
    - GitHub 저장소 -> 최신 릴리즈 APK 직링크
    - 구글 드라이브 -> 직접 다운로드 링크
    """
    if not url:
        return DEFAULT_DIRECT_DOWNLOAD_URL
    url = url.strip()

    gh_info = extract_github_repo(url)
    if gh_info:
        owner, repo = gh_info
        return f"https://github.com/{owner}/{repo}/releases/latest/download/JongJongTrader_ARM64.apk"

    gdrive_id = extract_gdrive_file_id(url)
    if gdrive_id:
        return f"https://drive.usercontent.google.com/download?id={gdrive_id}&export=download&confirm=t"

    return url


# 하위 호환성 별칭
parse_gdrive_download_url = parse_download_url


def check_remote_version_info(url: str = DEFAULT_UPDATE_CHANNEL_URL, timeout: int = 6) -> Dict[str, Any]:
    """
    GitHub Releases 또는 구글 드라이브 배포 링크의 최신 파일 정보를 확인하여
    현재 설치된 앱 버전과 비교합니다.
    """
    import urllib.request

    url = (url or "").strip() or DEFAULT_UPDATE_CHANNEL_URL
    gh_info = extract_github_repo(url)

    # 1. GitHub Releases 채널 검사
    if gh_info or ("drive.google.com" not in url and "google.com" not in url):
        owner, repo = gh_info if gh_info else DEFAULT_GITHUB_REPO.split('/')
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        direct_download_url = f"https://github.com/{owner}/{repo}/releases/latest/download/JongJongTrader_ARM64.apk"
        releases_page_url = f"https://github.com/{owner}/{repo}/releases"

        try:
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": "JongJongTrader-Mobile-App",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                rel = json.loads(res.read().decode('utf-8'))
                tag_name = rel.get("tag_name", "")
                rel_name = rel.get("name") or tag_name or "최신 업데이트"
                rel_body = rel.get("body", "").strip()
                published_at = rel.get("published_at", "")
                html_url = rel.get("html_url") or releases_page_url

                # 버전 번호 파싱 (예: v2.0.0 -> 2.0.0)
                ver_match = re.search(r'(\d+\.\d+(?:\.\d+)?)', tag_name)
                remote_ver = ver_match.group(1) if ver_match else APP_VERSION

                # 날짜 및 타임스탬프 파싱 (KST 한국시간)
                kst_str = "알 수 없음"
                remote_ts = 0.0
                if published_at:
                    try:
                        # ISO 8601 UTC -> KST
                        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        remote_ts = dt.timestamp()
                        kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
                        kst_str = kst_dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass

                # 에셋 검색 (JongJongTrader_ARM64.apk 또는 .apk 파일)
                apk_asset = None
                for asset in rel.get("assets", []):
                    name = asset.get("name", "")
                    if name.endswith(".apk"):
                        apk_asset = asset
                        if "ARM64" in name:
                            break

                if apk_asset:
                    download_url = apk_asset.get("browser_download_url") or direct_download_url
                    size_bytes = apk_asset.get("size", 0)
                    size_mb = round(size_bytes / (1024 * 1024), 2)
                    filename = apk_asset.get("name", "JongJongTrader_ARM64.apk")
                else:
                    download_url = direct_download_url
                    size_mb = 107.95
                    filename = "JongJongTrader_ARM64.apk"

                # 버전 비교
                current_ver_tuple = parse_version_tuple(APP_VERSION)
                remote_ver_tuple = parse_version_tuple(remote_ver)

                if remote_ver_tuple > current_ver_tuple:
                    is_newer = True
                elif remote_ver_tuple < current_ver_tuple:
                    is_newer = False
                else:
                    # 버전 번호가 같을 경우 타임스탬프 비교 (2분 이상 최신 업로드일 때)
                    is_newer = remote_ts > (APP_BUILD_TIMESTAMP + 120)

                return {
                    "status": "success",
                    "channel": "github",
                    "is_newer": is_newer,
                    "current_version": APP_VERSION,
                    "remote_version": remote_ver,
                    "tag_name": tag_name,
                    "release_name": rel_name,
                    "release_notes": rel_body,
                    "remote_filename": filename,
                    "remote_size_mb": size_mb,
                    "remote_date_str": kst_str,
                    "download_url": download_url,
                    "html_url": html_url,
                    "remote_timestamp": remote_ts
                }

        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                return {
                    "status": "no_release",
                    "channel": "github",
                    "current_version": APP_VERSION,
                    "message": f"GitHub 저장소({owner}/{repo})에 아직 등록된 릴리즈 배포판이 없습니다.",
                    "download_url": releases_page_url,
                    "html_url": releases_page_url
                }
            return {
                "status": "error",
                "channel": "github",
                "error": f"GitHub API 응답 오류 (HTTP {ex.code})",
                "current_version": APP_VERSION,
                "download_url": direct_download_url
            }
        except Exception as ex:
            return {
                "status": "error",
                "channel": "github",
                "error": str(ex),
                "current_version": APP_VERSION,
                "download_url": direct_download_url
            }

    # 2. 구글 드라이브 대체 채널 검사 (기존 호환)
    download_url = parse_download_url(url)
    try:
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            method="HEAD"
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            headers = dict(res.headers)
            last_mod_str = headers.get("Last-Modified", "")
            size_bytes = int(headers.get("Content-Length", 0))
            cd = headers.get("Content-Disposition", "")

            fn_match = re.search(r'filename="?([^";]+)"?', cd)
            filename = fn_match.group(1) if fn_match else "JongJongTrader_ARM64.apk"
            size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0.0

            kst_str = "알 수 없음"
            remote_ts = 0.0
            if last_mod_str:
                try:
                    dt = email.utils.parsedate_to_datetime(last_mod_str)
                    remote_ts = dt.timestamp()
                    kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
                    kst_str = kst_dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            remote_ver = None
            ver_candidates = re.findall(r'v?(\d+\.\d+(?:\.\d+)?)', filename)
            for cand in ver_candidates:
                if cand != "64":
                    remote_ver = cand
                    break

            is_newer = False
            current_ver_tuple = parse_version_tuple(APP_VERSION)
            if remote_ver:
                remote_ver_tuple = parse_version_tuple(remote_ver)
                if remote_ver_tuple > current_ver_tuple:
                    is_newer = True
                elif remote_ver_tuple < current_ver_tuple:
                    is_newer = False
                else:
                    is_newer = remote_ts > (APP_BUILD_TIMESTAMP + 120)
            else:
                is_newer = remote_ts > (APP_BUILD_TIMESTAMP + 120)

            return {
                "status": "success",
                "channel": "gdrive",
                "is_newer": is_newer,
                "current_version": APP_VERSION,
                "remote_version": remote_ver or APP_VERSION,
                "remote_filename": filename,
                "remote_size_mb": size_mb,
                "remote_date_str": kst_str,
                "download_url": download_url,
                "remote_timestamp": remote_ts
            }
    except Exception as ex:
        return {
            "status": "error",
            "channel": "gdrive",
            "error": str(ex),
            "current_version": APP_VERSION,
            "download_url": download_url
        }


def trigger_apk_download(download_url: str, page=None):
    """
    APK 직링크 다운로드를 트리거합니다.
    Flet Page가 전달되면 Flet의 네이티브 UrlLauncher 서비스를 호출하고,
    그 외 환경에서는 시스템 기본 웹브라우저를 호출합니다.
    """
    if page is not None:
        try:
            from flet.controls.services.url_launcher import UrlLauncher
            page.run_task(UrlLauncher().launch_url, download_url)
            return
        except Exception as e:
            print(f"[AppUpdate] Page UrlLauncher 호출 실패: {e}")

    try:
        import webbrowser
        webbrowser.open(download_url)
    except Exception as e:
        print(f"[AppUpdate] 브라우저 열기 실패: {e}")
