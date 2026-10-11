"""
GitHub Releases 배포 및 APK 업로드 자동화 스크립트
"""
import os
import sys
import json
import urllib.request
import urllib.error
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.app_update import APP_VERSION

REPO = "wprkfgur-dotcom/jj_invest"
DEFAULT_TAG = f"v{APP_VERSION}"
DEFAULT_FILES = [
    r"C:\ai_development\dist\JongJongTrader_ARM64.apk",
    r"C:\ai_development\dist\JongJongTrader_Mobile.exe"
]


def get_github_token() -> str:
    """Git Credential Manager에서 GitHub 액세스 토큰을 획득합니다."""
    try:
        p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
        creds = dict([l.split('=', 1) for l in out.strip().splitlines() if '=' in l])
        token = creds.get('password')
        if token and token.startswith(('gho_', 'ghp_', 'github_pat_')):
            return token
    except Exception as e:
        print(f"[Error] 토큰 획득 실패: {e}")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    raise RuntimeError("GitHub 인증 토큰을 찾을 수 없습니다.")


def get_changelog_notes_for_tag(tag: str) -> str:
    """CHANGELOG.md에서 해당 태그의 릴리즈 노트를 추출합니다."""
    changelog_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        return ""
    try:
        with open(changelog_path, "r", encoding="utf-8") as f:
            content = f.read()
        target_header = f"## [{tag}]"
        if target_header not in content:
            return ""
        start = content.find(target_header)
        end = content.find("\n## [", start + len(target_header))
        if end != -1:
            notes = content[start:end].strip()
        else:
            notes = content[start:].strip()
        return notes
    except Exception:
        return ""


def publish_release(tag: str = DEFAULT_TAG, files: list = None, title: str = None, notes: str = None):
    token = get_github_token()
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "JongJongTrader-Release-Script",
        "Accept": "application/vnd.github.v3+json"
    }

    if files is None:
        files = DEFAULT_FILES

    if not title:
        title = f"JongJong Trader {tag} (Modular Views Architecture - Dual Release)"
    if not notes:
        cl_notes = get_changelog_notes_for_tag(tag)
        if cl_notes:
            notes = (
                f"{cl_notes}\n\n"
                f"- **배포 바이너리 (듀얼 배포)**:\n"
                f"  - 📱 안드로이드 실기기: `JongJongTrader_ARM64.apk`\n"
                f"  - 💻 윈도우 모바일 뷰: `JongJongTrader_Mobile.exe`\n"
            )
        else:
            notes = (
                f"## 🚀 JongJong Trader {tag} 릴리즈\n\n"
                f"- **배포 바이너리 (듀얼 배포)**:\n"
                f"  - 📱 안드로이드 실기기: `JongJongTrader_ARM64.apk`\n"
                f"  - 💻 윈도우 모바일 뷰: `JongJongTrader_Mobile.exe`\n"
            )

    # 1. 릴리즈 존재 확인 또는 생성
    release_data = None
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
            headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode())
            print(f"ℹ️ 기존 릴리즈 태그 {tag} 발견 (ID: {release_data['id']})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"🆕 새로운 릴리즈 생성 중: {tag}...")
            payload = json.dumps({
                "tag_name": tag,
                "target_commitish": "main",
                "name": title,
                "body": notes,
                "draft": False,
                "prerelease": False
            }).encode('utf-8')
            create_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases",
                data=payload,
                headers={**headers, "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(create_req) as resp:
                release_data = json.loads(resp.read().decode())
                print(f"✅ 릴리즈 생성 성공 (ID: {release_data['id']})")
        else:
            raise

    upload_url = release_data["upload_url"].split("{")[0]
    existing_assets = {a["name"]: a["id"] for a in release_data.get("assets", [])}

    # 2. 파일별 업로드
    results = []
    for fpath in files:
        if not os.path.exists(fpath):
            print(f"⚠️ 배포 파일을 찾을 수 없어 건너뜁니다: {fpath}")
            continue

        fname = os.path.basename(fpath)
        fsize = os.path.getsize(fpath)
        fsize_mb = round(fsize / (1024 * 1024), 2)
        print(f"\n📦 배포 대상: {fname} ({fsize_mb} MB)")

        # 기존 동일 이름 에셋 삭제
        if fname in existing_assets:
            asset_id = existing_assets[fname]
            print(f"🗑️ 기존 에셋 삭제 중: {fname} (ID: {asset_id})...")
            del_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}",
                headers=headers,
                method="DELETE"
            )
            with urllib.request.urlopen(del_req) as resp:
                pass
            print("✅ 기존 에셋 삭제 완료")

        content_type = "application/vnd.android.package-archive" if fname.endswith(".apk") else "application/vnd.microsoft.portable-executable"
        print(f"⬆️ 파일 업로드 시작... ({fname}, {fsize_mb} MB)")

        upload_target = f"{upload_url}?name={fname}"
        with open(fpath, "rb") as f:
            file_data = f.read()

        upload_req = urllib.request.Request(
            upload_target,
            data=file_data,
            headers={
                "Authorization": f"token {token}",
                "User-Agent": "JongJongTrader-Release-Script",
                "Content-Type": content_type,
                "Content-Length": str(len(file_data))
            }
        )
        with urllib.request.urlopen(upload_req) as resp:
            res = json.loads(resp.read().decode())
            print(f"🎉 {fname} 업로드 완료! 링크:\n  {res.get('browser_download_url')}")
            results.append(res)

    print(f"\n✨ 모든 파일 배포 완료! GitHub Releases URL:\n  https://github.com/{REPO}/releases/tag/{tag}")
    return results


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TAG
    publish_release(tag)

