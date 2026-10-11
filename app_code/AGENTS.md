# JongJong Trader - Agent Guidelines & Policies

이 문서는 본 프로젝트(`jj_invest`)의 개발 및 릴리스 기본 지침입니다.

## 📌 핵심 원칙 요약

1. **배포 타깃 단일화 (Mobile First)**
   - 본 프로젝트의 최종 배포 대상은 **오직 2가지**입니다:
     1) **안드로이드 앱**: `dist\JongJongTrader_ARM64.apk`
     2) **윈도우 모바일 뷰 실행파일**: `dist\JongJongTrader_Mobile.exe`
   - *구 PC 데스크톱 버전(`JongJongTrader.exe`)은 폐기되었으며 더 이상 빌드하거나 관리하지 않습니다.*

2. **개발 및 자동 검증 (Windows First & Build/Test Automation)**
   - 모든 기능 개발과 버그 수정은 **Windows 환경의 모바일 뷰를 기본으로** 진행합니다.
   - 로컬 테스트: `run_mobile.bat` (스마트폰 412x860 비율 윈도우 프리뷰 모드).
   - 기능 수정 완료 후 **바이너리 빌드 및 테스트(단위 테스트/기능 검증)까지는 AI가 자율적으로 진행**합니다:
     - 테스트: `python tools\run_app_tests.py`
     - 윈도우 실행파일 빌드: `python build_mobile_exe.py` 실행하여 `dist\JongJongTrader_Mobile.exe` 생성
     - 안드로이드 APK 빌드: `powershell -ExecutionPolicy Bypass -File .\build_arm64_release_apk.ps1`

3. **버전 관리 및 배포 통제 (User Approval Required for Versioning & Git Push)**
   - ⚠️ **핵심 원칙**: AI는 빌드 및 테스트 검증까지만 자율적으로 수행하며, **버전 번호 변경(Versioning)과 Git Commit/Push(및 GitHub Release 발행)는 반드시 사용자에게 의사를 묻고 사용자가 결정**합니다.
   - 사용자가 릴리스 또는 푸시를 승인/요청한 경우에만 아래 릴리스 절차를 진행합니다:
     - **버전 번호 규칙 (`MAJOR.MINOR.PATCH`)**:
       - `MAJOR`: 대규모 변경사항 및 구조적 개편 (예: `2.0.0` -> `3.0.0`)
       - `MINOR`: 신규 기능 추가 (예: `2.1.0` -> `2.2.0`)
       - `PATCH`: 단순 버그 픽스 및 사소한 수정 (예: `2.1.0` -> `2.1.1`)
     - **버전 증가 대상 파일**: `core/app_update.py` (`APP_VERSION`, `APP_BUILD_NAME`) 및 `pubspec.yaml`
     - **릴리스 노트**: `CHANGELOG.md` 작성 및 GitHub Release 본문 반영
     - **Git 반영**: 작업된 모든 소스를 `origin/main`에 commit & push
     - **듀얼 배포 (APK & EXE 동시 배포)**: GitHub Releases에 최신 태그(`vX.X.X`)로 `dist\JongJongTrader_ARM64.apk`와 `dist\JongJongTrader_Mobile.exe`를 항상 함께 업로드 (`python tools\publish_github_release.py`)

4. **디렉토리 청결 (Clean Workspace)**
   - `.apk`, `.exe` 등 컴파일 바이너리는 프로젝트 루트에 두지 않고 반드시 `dist/`에만 유지합니다.

상세 정책 내용은 [DEVELOPMENT_POLICY.md](file:///c:/ai_development/DEVELOPMENT_POLICY.md) 및 [.agents/rules/dev-and-release-policy.md](file:///c:/ai_development/.agents/rules/dev-and-release-policy.md)를 참조하십시오.
