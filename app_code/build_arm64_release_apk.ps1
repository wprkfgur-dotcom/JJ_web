$ErrorActionPreference = "Stop"
Write-Host "=========================================="
Write-Host "JongJong Trader - ARM64 Release APK Build"
Write-Host "=========================================="

$env:PYTHONIOENCODING = "utf-8"
$env:JAVA_HOME = "C:\Users\huxley\java\17.0.13+11"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$gitCmd = "$env:LOCALAPPDATA\Programs\Git\cmd"
$flutterBin = "C:\Users\huxley\flutter\3.44.8\bin"
$env:PATH = "$flutterBin;$gitCmd;$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:PATH"

$env:SERIOUS_PYTHON_APP = "C:\ai_development\flet_apk_project\build\python-app"
$env:SERIOUS_PYTHON_SITE_PACKAGES = "C:\ai_development\flet_apk_project\build\site-packages"

Write-Host "[1/3] Synchronizing Python application sources (sync_app.py)..."
python "C:\ai_development\sync_app.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "sync_app.py failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "[2/3] Building Flutter APK (target-platform: android-arm64, mode: release)..."
Set-Location "C:\ai_development\flet_apk_project\build\flutter"

& "$flutterBin\flutter.bat" build apk --target-platform android-arm64 --release

if ($LASTEXITCODE -ne 0) {
    Write-Error "Flutter build failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "[3/3] Locating built APK and copying to destinations..."
$foundApk = "C:\ai_development\flet_apk_project\build\flutter\build\app\outputs\flutter-apk\app-release.apk"
if (-not (Test-Path $foundApk)) {
    $latest = Get-ChildItem -Path "C:\ai_development\flet_apk_project\build" -Filter "*.apk" -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        $foundApk = $latest.FullName
    }
}

if ($foundApk -and (Test-Path $foundApk)) {
    $item = Get-Item $foundApk
    $sizeMb = [math]::Round($item.Length / 1MB, 2)
    Write-Host "Build Successful! Output APK: $foundApk ($sizeMb MB)"

    if (-not (Test-Path "C:\ai_development\dist")) {
        New-Item -ItemType Directory -Path "C:\ai_development\dist" -Force | Out-Null
    }

    Copy-Item -Path $foundApk -Destination "C:\ai_development\dist\JongJongTrader_ARM64.apk" -Force

    Write-Host "=========================================="
    Write-Host "Deployment file generated successfully:"
    Write-Host "  - C:\ai_development\dist\JongJongTrader_ARM64.apk ($sizeMb MB)"
    Write-Host "=========================================="
} else {
    Write-Error "Could not find generated APK."
    exit 1
}
