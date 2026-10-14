# 휴대용 EXE(단일 파일)와 설치파일용 폴더형 빌드를 만듭니다.
# 사용: powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root 'dist'
$work = Join-Path $root 'build'
$icon = Join-Path $PSScriptRoot 'app.ico'
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

& $python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller가 필요합니다: pip install pyinstaller' }

$common = @(
    '--noconfirm', '--clean', '--windowed',
    '--icon', $icon,
    '--add-data', "$(Join-Path $root 'static');static",
    '--exclude-module', 'webview', '--exclude-module', 'numpy', '--exclude-module', 'PIL',
    '--specpath', $work,
    (Join-Path $root 'app.py')
)

Push-Location $root
try {
    # 1) 휴대용: 파일 하나로 복사해서 실행
    & $python -m PyInstaller @common --onefile --name 'MemoCalendar-Portable' `
        --distpath $dist --workpath (Join-Path $work 'portable')
    if ($LASTEXITCODE -ne 0) { throw '휴대용 EXE 빌드 실패' }

    # 2) 설치파일용: 폴더형(시작이 빠르고 백신 오탐이 적음)
    & $python -m PyInstaller @common --onedir --name 'MemoCalendar' `
        --distpath (Join-Path $dist 'app') --workpath (Join-Path $work 'folder')
    if ($LASTEXITCODE -ne 0) { throw '폴더형 빌드 실패' }
} finally { Pop-Location }

# 3) 정식 설치파일 (Inno Setup 6 필요)
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw '설치파일 빌드 실패' }
} else {
    Write-Warning 'Inno Setup 6가 없어 설치파일(.exe)은 만들지 않았습니다. (winget install JRSoftware.InnoSetup)'
}
Get-ChildItem $dist -File | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
