<#
.SYNOPSIS
    Uryx Windows installer ve electron-updater dosyalarını GitHub Release'e yükler.

.DESCRIPTION
    electron-updater, GitHub Releases kanalında `latest.yml` olmadan
    "Cannot find latest.yml in the release" hatası verir. Bu script installer
    yanında manifest ve blockmap olmadan yüklemeyi reddeder.

    Kaynak (öncelik sırası): dist\  sonra  apps\desktop\release\

.PARAMETER Tag
    Mevcut GitHub release etiketi (ör. v0.6.0).

.EXAMPLE
    .\scripts\publish-github-release.ps1 -Tag v0.6.0
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^v\d+\.\d+\.\d+(\.\d+)?$')]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $RepoRoot 'dist'
$ReleaseDir = Join-Path $RepoRoot 'apps\desktop\release'
$Repo = 'uguredm/Uryx'

function Stop-WithError {
    param([string]$Message, [string[]]$Hints = @())
    Write-Host "  [HATA] $Message" -ForegroundColor Red
    foreach ($hint in $Hints) { Write-Host "         -> $hint" -ForegroundColor DarkGray }
    exit 1
}

function Resolve-Asset {
    param([string]$Name)
    foreach ($dir in @($DistDir, $ReleaseDir)) {
        $path = Join-Path $dir $Name
        if (Test-Path -LiteralPath $path) { return (Get-Item -LiteralPath $path) }
    }
    return $null
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Stop-WithError 'GitHub CLI (gh) bulunamadı.' @('https://cli.github.com')
}

$required = @(
    'Uryx-Setup.exe',
    'Uryx-Setup.exe.sha256',
    'Uryx-Setup.exe.blockmap',
    'latest.yml'
)

$paths = @()
foreach ($name in $required) {
    $item = Resolve-Asset $name
    if (-not $item) {
        Stop-WithError "Eksik dosya: $name" @(
            'Önce .\scripts\build-windows.ps1 çalıştırın.',
            'Yalnızca .exe yüklemek otomatik güncellemeyi kırar.'
        )
    }
    $paths += $item.FullName
}

$yml = Get-Content -LiteralPath (Resolve-Asset 'latest.yml').FullName -Raw
$version = $Tag.TrimStart('v')
if ($yml -notmatch "(?m)^version:\s*$([regex]::Escape($version))\s*$") {
    Stop-WithError "latest.yml sürümü etiketle uyuşmuyor (beklenen $version)." @(
        'Yanlış klasördeki eski latest.yml yüklemeyin.'
    )
}
if ($yml -notmatch '(?m)^path:\s*Uryx-Setup\.exe\s*$') {
    Stop-WithError 'latest.yml NSIS path alanı Uryx-Setup.exe değil.'
}

Write-Host "==> $Tag varlıkları yükleniyor ($Repo)" -ForegroundColor Cyan
& gh release view $Tag --repo $Repo --json tagName | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Release $Tag bulunamadı." @("Önce: gh release create $Tag --repo $Repo --title ...")
}

& gh release upload $Tag --repo $Repo --clobber @paths
if ($LASTEXITCODE -ne 0) {
    Stop-WithError 'gh release upload başarısız.'
}

$names = & gh release view $Tag --repo $Repo --json assets --jq '.assets[].name'
if ($LASTEXITCODE -ne 0) {
    Stop-WithError 'Yükleme sonrası release okunamadı.'
}
foreach ($need in $required) {
    if ($names -notcontains $need) {
        Stop-WithError "Yükleme sonrası $need release'de yok."
    }
}

Write-Host "  [OK] latest.yml: https://github.com/$Repo/releases/download/$Tag/latest.yml" -ForegroundColor Green
Write-Host "       Release:    https://github.com/$Repo/releases/tag/$Tag"
Write-Host ''
