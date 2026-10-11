"""
Google Drive 클라우드 실시간 동기화 모듈 (Google Apps Script Web App 연동)

사용자의 개인 Google Drive 내 전용 폴더('JongJongTrader')를 생성하여
accounts.json 계좌 데이터를 실시간으로 안전하게 양방향 동기화합니다.

주요 기능:
1. Google Drive Sync ON / OFF 토글 관리
2. Google Apps Script(GAS) Web App 기반 안전한 무인증/개인인증 동기화 (OAuth 만료 문제 없음)
3. 계좌 변동 시 백그라운드 자동 업로드 (실시간 반영)
4. 앱 실행 시 및 필요 시 최신 데이터 자동/수동 다운로드 및 동기화
5. 데이터 유실 방지를 위한 로컬 자동 백업(accounts.backup.json)
6. 1분 만에 배포 가능한 Google Apps Script 템플릿 및 가이드 제공
"""

import os
import sys
import json
import threading
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

try:
    import requests
except ImportError:
    requests = None

# 저장소 경로 계산
if os.environ.get("FLET_APP_STORAGE_DATA"):
    BASE_DIR = os.environ.get("FLET_APP_STORAGE_DATA")
elif getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
SYNC_CONFIG_FILE = os.path.join(DATA_DIR, "cloud_sync_config.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
ACCOUNTS_BACKUP_FILE = os.path.join(DATA_DIR, "accounts.backup.json")


DEFAULT_CONFIG = {
    "sync_enabled": False,
    "web_app_url": "",
    "last_sync_time": None,
    "last_sync_status": "none",   # "success", "error", "none"
    "last_sync_message": "동기화 설정이 비활성화되어 있습니다.",
    "auto_sync_on_save": True,
    "folder_name": "JongJongTrader"
}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_sync_config() -> Dict[str, Any]:
    """클라우드 동기화 설정을 로드합니다."""
    _ensure_dir()
    if not os.path.exists(SYNC_CONFIG_FILE):
        save_sync_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 기본 키 누락 방지
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as e:
        print(f"[CloudSync] 설정 파일 로드 실패: {e}")
        return dict(DEFAULT_CONFIG)


def save_sync_config(config: Dict[str, Any]):
    """클라우드 동기화 설정을 저장합니다."""
    _ensure_dir()
    try:
        with open(SYNC_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CloudSync] 설정 파일 저장 실패: {e}")


def is_sync_enabled() -> bool:
    """동기화 기능 활성화 및 올바른 URL 등록 여부를 반환합니다."""
    cfg = get_sync_config()
    url = cfg.get("web_app_url", "").strip()
    return bool(cfg.get("sync_enabled", False)) and len(url) > 20 and url.startswith("http")


def test_connection(url: Optional[str] = None) -> Tuple[bool, str]:
    """
    Google Apps Script 웹 앱과의 연결 상태를 확인(Ping)합니다.
    """
    if not url:
        cfg = get_sync_config()
        url = cfg.get("web_app_url", "").strip()

    if not url or not url.startswith("http"):
        return False, "유효한 Google Apps Script Web App URL을 입력해주세요."

    try:
        if requests:
            resp = requests.get(url, params={"action": "ping"}, timeout=12)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("status") == "ok":
                        msg = data.get("message", "연결 성공")
                        return True, f"Google Drive 연동 성공! ({msg})"
                    else:
                        return False, f"응답 오류: {data.get('message', '알 수 없는 응답')}"
                except Exception:
                    # 응답 텍스트 확인
                    if "ok" in resp.text.lower() or "connected" in resp.text.lower():
                        return True, "Google Drive 연동 성공!"
                    return False, f"잘못된 응답 형식: {resp.text[:100]}"
            else:
                return False, f"HTTP {resp.status_code} 오류가 발생했습니다."
        else:
            import urllib.request
            req_url = f"{url}?action=ping" if "?" not in url else f"{url}&action=ping"
            req = urllib.request.Request(req_url, headers={"User-Agent": "JongJongTrader/1.0"})
            with urllib.request.urlopen(req, timeout=12) as response:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                if data.get("status") == "ok":
                    return True, "Google Drive 연동 성공!"
                return False, data.get("message", "오류 응답")
    except Exception as e:
        return False, f"연결 실패: {str(e)}"


def upload_accounts_to_drive(accounts: List[Dict[str, Any]], url: Optional[str] = None) -> Tuple[bool, str]:
    """
    현재 계좌 데이터를 Google Drive의 전용 폴더('JongJongTrader/accounts.json')로 업로드합니다.
    """
    if not url:
        cfg = get_sync_config()
        url = cfg.get("web_app_url", "").strip()

    if not url or not url.startswith("http"):
        return False, "Google Apps Script Web App URL이 설정되지 않았습니다."

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "action": "upload",
        "timestamp": now_str,
        "count": len(accounts),
        "data": accounts
    }

    try:
        if requests:
            # allow_redirects=True로 Google Apps Script의 302 응답 자동 추적
            resp = requests.post(url, json=payload, timeout=20, allow_redirects=True)
            if resp.status_code == 200:
                try:
                    res_json = resp.json()
                    if res_json.get("status") == "ok":
                        _update_sync_status(True, f"{len(accounts)}개 계좌 업로드 완료 ({now_str})")
                        return True, f"구글 드라이브 업로드 완료 ({len(accounts)}개 계좌)"
                    else:
                        err_msg = res_json.get("message", "응답 상태 이상")
                        _update_sync_status(False, err_msg)
                        return False, err_msg
                except Exception:
                    _update_sync_status(True, f"업로드 완료 ({now_str})")
                    return True, "구글 드라이브 업로드 완료"
            else:
                err_msg = f"HTTP {resp.status_code} 오류"
                _update_sync_status(False, err_msg)
                return False, err_msg
        else:
            import urllib.request
            post_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=post_data,
                headers={"Content-Type": "application/json", "User-Agent": "JongJongTrader/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read().decode("utf-8")
                res_json = json.loads(body)
                if res_json.get("status") == "ok":
                    _update_sync_status(True, f"{len(accounts)}개 계좌 업로드 완료 ({now_str})")
                    return True, "구글 드라이브 업로드 완료"
                err_msg = res_json.get("message", "업로드 오류")
                _update_sync_status(False, err_msg)
                return False, err_msg

    except Exception as e:
        err_msg = f"업로드 실패: {str(e)}"
        _update_sync_status(False, err_msg)
        return False, err_msg


def download_accounts_from_drive(url: Optional[str] = None) -> Tuple[bool, Optional[List[Dict[str, Any]]], str]:
    """
    Google Drive의 전용 폴더('JongJongTrader/accounts.json')에서 최신 계좌 데이터를 다운로드합니다.
    """
    if not url:
        cfg = get_sync_config()
        url = cfg.get("web_app_url", "").strip()

    if not url or not url.startswith("http"):
        return False, None, "Google Apps Script Web App URL이 설정되지 않았습니다."

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        if requests:
            resp = requests.get(url, params={"action": "download"}, timeout=20, allow_redirects=True)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("status") == "ok":
                    accs = res_json.get("data", [])
                    if isinstance(accs, str):
                        try:
                            accs = json.loads(accs)
                        except Exception:
                            accs = []
                    _update_sync_status(True, f"{len(accs)}개 계좌 다운로드 완료 ({now_str})")
                    return True, accs, f"구글 드라이브에서 {len(accs)}개 계좌를 정상 수신했습니다."
                else:
                    err_msg = res_json.get("message", "다운로드 응답 오류")
                    _update_sync_status(False, err_msg)
                    return False, None, err_msg
            else:
                err_msg = f"HTTP {resp.status_code} 오류"
                _update_sync_status(False, err_msg)
                return False, None, err_msg
        else:
            import urllib.request
            req_url = f"{url}?action=download" if "?" not in url else f"{url}&action=download"
            req = urllib.request.Request(req_url, headers={"User-Agent": "JongJongTrader/1.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read().decode("utf-8")
                res_json = json.loads(body)
                if res_json.get("status") == "ok":
                    accs = res_json.get("data", [])
                    _update_sync_status(True, f"{len(accs)}개 계좌 다운로드 완료 ({now_str})")
                    return True, accs, "다운로드 성공"
                err_msg = res_json.get("message", "다운로드 오류")
                _update_sync_status(False, err_msg)
                return False, None, err_msg

    except Exception as e:
        err_msg = f"다운로드 실패: {str(e)}"
        _update_sync_status(False, err_msg)
        return False, None, err_msg


def sync_local_with_drive(account_manager) -> Tuple[bool, str]:
    """
    Google Drive의 데이터와 로컬 데이터를 안전하게 동기화합니다.
    드라이브에 저장된 데이터가 존재하면 로컬 백업을 생성한 뒤 로컬 파일에 적용합니다.
    """
    if not is_sync_enabled():
        return False, "Google Drive 동기화가 비활성화되어 있습니다."

    ok, drive_accs, msg = download_accounts_from_drive()
    if not ok:
        return False, msg

    if drive_accs is None:
        return False, "드라이브에 유효한 데이터가 없습니다."

    # 로컬 계좌 가져오기
    local_accs = account_manager.load_accounts()

    # 만약 드라이브 계좌가 비어있고 로컬에 계좌가 있다면, 로컬 계좌를 드라이브로 최초 업로드
    if len(drive_accs) == 0 and len(local_accs) > 0:
        up_ok, up_msg = upload_accounts_to_drive(local_accs)
        if up_ok:
            return True, f"로컬 계좌 {len(local_accs)}개를 구글 드라이브에 최초 동기화했습니다."
        return False, f"드라이브 최초 업로드 실패: {up_msg}"

    # 안전을 위해 기존 로컬 파일 백업
    try:
        if os.path.exists(account_manager.filepath):
            with open(account_manager.filepath, "r", encoding="utf-8") as rf:
                with open(ACCOUNTS_BACKUP_FILE, "w", encoding="utf-8") as wf:
                    wf.write(rf.read())
    except Exception as e:
        print(f"[CloudSync] 백업 실패: {e}")

    # 드라이브 계좌로 로컬 파일 갱신 (저장 시 트리거는 잠시 비활성 플래그 적용)
    account_manager.save_accounts(drive_accs, skip_cloud_sync=True)
    return True, f"구글 드라이브 동기화 완료! ({len(drive_accs)}개 계좌 적용됨)"


def trigger_async_upload(accounts: List[Dict[str, Any]]):
    """
    계좌 저장 시 UI 멈춤 없이 백그라운드 스레드에서 구글 드라이브로 비동기 업로드합니다.
    """
    if not is_sync_enabled():
        return

    def _worker():
        try:
            upload_accounts_to_drive(accounts)
        except Exception as e:
            print(f"[CloudSync Async] 업로드 예외: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def _update_sync_status(is_success: bool, message: str):
    """최근 동기화 상태 및 일시를 설정 파일에 갱신합니다."""
    cfg = get_sync_config()
    cfg["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg["last_sync_status"] = "success" if is_success else "error"
    cfg["last_sync_message"] = message
    save_sync_config(cfg)


def get_gas_script_code() -> str:
    """
    사용자가 구글 드라이브에 1분 만에 복사하여 배포할 수 있는
    Google Apps Script 완전체 코드를 반환합니다.
    """
    return """// =====================================================================
// JongJong Trader - Google Drive Cloud Sync Script
// 종종 무한매수봇 전용 구글 드라이브 실시간 양방향 동기화 스크립트
// =====================================================================
// [초간단 1분 배포 방법]
// 1. 구글 드라이브(drive.google.com) 접속
// 2. 좌측 상단 '+ 새로 만들기' -> '더보기' -> 'Google Apps Script' 클릭
// 3. 기존 코드를 모두 지우고 이 스크립트 전체를 복사하여 붙여넣기
// 4. 우측 상단 파란색 [배포] -> [새 배포] 클릭
// 5. 톱니바퀴 아이콘 클릭 -> [웹 앱(Web App)] 선택
//    - 설명: JongJong Trader Sync
//    - 다음 사용자 권한으로 실행: '나(내 이메일)'
//    - 액세스 권한이 있는 사용자: '모든 사용자(Anyone)' 선택 (필수!)
// 6. [배포] 클릭 후 '액세스 승인' 창이 뜨면 본인 계정 선택 및 허용
// 7. 발급된 '웹 앱 URL' (https://script.google.com/macros/s/.../exec) 복사
// 8. 앱의 설정 -> 'Google Apps Script 웹 앱 URL' 에 붙여넣고 Sync ON!
// =====================================================================

var FOLDER_NAME = "JongJongTrader";
var FILE_NAME = "accounts.json";

function getOrCreateFolder() {
  var folders = DriveApp.getFoldersByName(FOLDER_NAME);
  if (folders.hasNext()) {
    return folders.next();
  }
  return DriveApp.createFolder(FOLDER_NAME);
}

function getOrCreateFile(folder) {
  var files = folder.getFilesByName(FILE_NAME);
  if (files.hasNext()) {
    return files.next();
  }
  return folder.createFile(FILE_NAME, "[]", MimeType.PLAIN_TEXT);
}

function doGet(e) {
  try {
    var action = (e && e.parameter && e.parameter.action) || "download";
    
    // 1. 연결 확인(Ping)
    if (action === "ping") {
      return ContentService.createTextOutput(JSON.stringify({
        status: "ok",
        message: "JongJong Trader Google Drive Sync Connected!",
        timestamp: new Date().toISOString()
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. 계좌 데이터 다운로드
    var folder = getOrCreateFolder();
    var file = getOrCreateFile(folder);
    var content = file.getBlob().getDataAsString();
    var updated = file.getLastUpdated().toISOString();
    
    var parsedData = [];
    try {
      parsedData = JSON.parse(content || "[]");
    } catch(parseErr) {
      parsedData = [];
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "ok",
      action: "download",
      updated_at: updated,
      data: parsedData
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    var folder = getOrCreateFolder();
    var file = getOrCreateFile(folder);
    
    var postData = "";
    if (e && e.postData && e.postData.contents) {
      postData = e.postData.contents;
    }
    
    if (!postData) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "전송된 데이터가 없습니다."
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    var payload = JSON.parse(postData);
    var accountsData = payload.data !== undefined ? payload.data : payload;
    var dataStr = typeof accountsData === "string" ? accountsData : JSON.stringify(accountsData, null, 2);
    
    // accounts.json 덮어쓰기
    file.setContent(dataStr);
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "ok",
      action: "upload",
      message: "Sync success",
      updated_at: new Date().toISOString(),
      count: Array.isArray(accountsData) ? accountsData.length : 1
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
"""
