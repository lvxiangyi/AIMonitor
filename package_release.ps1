$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$ElectronDir = Join-Path $Root "electron"
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$ReleaseDir = Join-Path $ElectronDir "release"

$PackageJson = Get-Content -Raw -Encoding UTF8 (Join-Path $ElectronDir "package.json") | ConvertFrom-Json
$Version = $PackageJson.version
$Date = Get-Date -Format "yyyy-MM-dd"
$ArtifactName = "FocusGuard-Agent-$Version-$Date-win-unpacked"
$SourceDir = Join-Path $ReleaseDir "win-unpacked"
$TargetDir = Join-Path $ReleaseDir $ArtifactName
$ZipPath = Join-Path $ReleaseDir "$ArtifactName.zip"

function Assert-UnderDirectory {
    param(
        [string]$Path,
        [string]$Parent
    )
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $FullParent = [System.IO.Path]::GetFullPath($Parent)
    if (-not $FullPath.StartsWith($FullParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside release directory: $FullPath"
    }
}

Write-Host "Release version: $Version"
Write-Host "Release date:    $Date"

Push-Location $BackendDir
try {
    & ".\.venv\Scripts\python.exe" -m unittest discover -s tests
    & ".\.venv\Scripts\pyinstaller.exe" "aimonitor-backend.spec" --noconfirm
}
finally {
    Pop-Location
}

Push-Location $FrontendDir
try {
    npm run build
}
finally {
    Pop-Location
}

Push-Location $ElectronDir
try {
    npx electron-builder --dir
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force $ReleaseDir | Out-Null

if (Test-Path $TargetDir) {
    Assert-UnderDirectory -Path $TargetDir -Parent $ReleaseDir
    Remove-Item -LiteralPath $TargetDir -Recurse -Force
}

if (Test-Path $ZipPath) {
    Assert-UnderDirectory -Path $ZipPath -Parent $ReleaseDir
    Remove-Item -LiteralPath $ZipPath -Force
}

Copy-Item -LiteralPath $SourceDir -Destination $TargetDir -Recurse
Compress-Archive -Path $TargetDir -DestinationPath $ZipPath -Force

Write-Host "Created:"
Write-Host "  $TargetDir"
Write-Host "  $ZipPath"
