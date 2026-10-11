# 종종이 & 무한매수 트레이더 - 개발 및 릴리스 정책 가이드

본 문서는 프로젝트의 일관된 개발 주기, 품질 검증, 버전 관리 및 배포 규칙을 정리한 공식 가이드입니다.

---

## 1. 지원 플랫폼 및 공식 배포 타깃

본 프로젝트는 모바일 우선(Mobile-First) 단일 코드베이스 전략을 취하며, 배포 타깃은 **아래 2종으로 단일화**되었습니다:

1. **안드로이드 릴리스 APK**: `dist\JongJongTrader_ARM64.apk`
2. **윈도우 모바일 뷰 EXE**: `dist\JongJongTrader_Mobile.exe`

> **[안내] 구 PC 데스크톱 버전(`JongJongTrader.exe`) 폐기**
> 초기 개발용이었던 Tkinter 기반의 데스크톱 전용 GUI(`run_gui.*`, `gui/tabs/*` 등)는 유지보수 비용 최소화 및 일관된 모바일 UX 유지를 위해 완전히 제거되었습니다.

---

## 2. 개발 및 검증 프로세스 (Development Workflow)

### 2.1 기본 개발 환경: Windows First (모바일 뷰)
- 모든 기능 추가, UI 수정, 버그 패치는 **Windows 로컬 모바일 뷰 환경**을 기준으로 먼저 개발하고 테스트합니다.
- **로컬 실행 스크립트**:
  - `run_mobile.bat` (스마트폰 412x860 해상도 프리뷰 실행)
- Python 콘솔 로그, 데이터 정산 로직, 구글 드라이브 동기화 등을 윈도우 환경에서 1차적으로 완벽하게 검증합니다.

### 2.2 안드로이드 빌드 및 실기기 검증 (Android Verification)
- 윈도우 환경에서의 수정 작업이 완전히 완료되면, 안드로이드 전용 ARM64 릴리스 APK를 빌드합니다.
- **빌드 명령어**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\build_arm64_release_apk.ps1
  ```
- **빌드 산출물 위치**: `dist\JongJongTrader_ARM64.apk`
- **실기기 설치 및 검증**:
  ```powershell
  adb install -r dist\JongJongTrader_ARM64.apk
  ```
- 모바일 화면 비율, 터치 이벤트, 알림/팝업, 파일 다운로드 등 모바일 고유 동작을 최종 확인합니다.

---

## 3. 릴리스 정책 (Release Workflow)

> ⚠️ **중요: AI 자율 작업 범위 및 사용자 승인 원칙**
> - **AI 자율 수행 범위**: 기능 개발 및 버그 수정 후 **단위 테스트(`python tools\run_app_tests.py`) 및 바이너리 빌드(`build_mobile_exe.py`, `build_arm64_release_apk.ps1`)까지만 자율적으로 진행**합니다.
> - **사용자 승인 필수**: **버전 번호 증가(Versioning), CHANGELOG 작성, Git Commit & Push, GitHub Release 배포는 AI가 임의로 수행하지 않고 반드시 사용자에게 의사를 묻고 사용자가 결정**합니다.

```
[개발/수정 완료] ───> [단위 테스트 & 바이너리 빌드 (AI 자율 수행)]
                                  │
                                  ▼
                    [사용자 확인 및 배포 승인 요청]
                                  │
                                  ▼ (사용자 승인 시)
[버전 번호 증가 (SemVer)] ──> [CHANGELOG.md] ──> [Git Push] ──> [GitHub Release 듀얼 배포]
```

### 단계별 절차 (사용자 승인 후 진행):

#### 1) 버전 번호 증가 (Version Bump - SemVer 규칙)
- **버전 번호 관리 체계 (`MAJOR.MINOR.PATCH`)**:
  - **`MAJOR` (맨 앞 자리)**: 큰 변경사항, 아키텍처 개편, 대규모 마일스톤 (예: `2.x.x` -> `3.0.0`)
  - **`MINOR` (가운데 자리)**: 새로운 전략/기능 추가 (예: `2.1.0` -> `2.2.0`)
  - **`PATCH` (마지막 자리)**: 단순 버그 픽스 및 사소한 수정 (예: `2.1.0` -> `2.1.1`)
- **반영 파일**:
  - [core/app_update.py](file:///c:/ai_development/core/app_update.py):
    - `APP_VERSION`: 새 버전 지정 (예: `2.1.1`)
    - `APP_BUILD_NAME`: 예: `"JongJong Trader v2.1.1 (ARM64 & Windows Release)"`
  - [flet_apk_project/build/flutter/pubspec.yaml](file:///c:/ai_development/flet_apk_project/build/flutter/pubspec.yaml):
    - `version: X.X.X+N` (버전 및 빌드 번호 일치)

#### 2) 릴리스 노트 작성 (Release Notes)
- [CHANGELOG.md](file:///c:/ai_development/CHANGELOG.md) 파일에 신규 버전에 대한 상세 변경 내역을 작성합니다.

#### 3) Git 커밋 및 푸시
- 변경된 모든 소스 코드와 문서를 Git에 커밋하고 원격 저장소에 푸시합니다:
  ```powershell
  git add .
  git commit -m "chore(release): bump version to vX.X.X - <요약 설명>"
  git push origin main
  ```

#### 4) 최신 바이너리 빌드 (APK & EXE)
1. 최신 소스가 반영된 안드로이드 릴리스 APK 빌드:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build_arm64_release_apk.ps1
   ```
   *(산출물: `dist\JongJongTrader_ARM64.apk`)*
2. 최신 소스가 반영된 윈도우용 모바일 실행파일 빌드:
   ```powershell
   python build_mobile_exe.py
   ```
   *(산출물: `dist\JongJongTrader_Mobile.exe`)*

#### 5) GitHub Releases 듀얼 배포
- 빌드된 APK와 EXE 두 바이너리를 모두 첨부하여 GitHub Release에 동시 정식 배포합니다:
  ```powershell
  python tools\publish_github_release.py vX.X.X
  ```

---

## 4. 작업 환경 청결 원칙 (Workspace Cleanliness)

- **루트 디렉토리 바이너리 금지**:
  - `JongJongTrader*.apk`, `JongJongTrader*.exe` 등 컴파일된 실행 파일은 루트 디렉토리에 생성/방치하지 않고 오직 [dist/](file:///c:/ai_development/dist/) 폴더에서만 관리합니다.
- **임시 파일 정리**:
  - 디버깅용 임시 파일이나 스크래치 스크립트는 완료 후 즉시 정리합니다.
