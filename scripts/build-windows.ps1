<#
.SYNOPSIS
    Uryx için Windows kurulum dosyası (installer) üretir.

.DESCRIPTION
    Sırasıyla:
      1. Ortamı doğrular (Node 20+, npm).
      2. Bağımlılıkları kurar.
      3. İkonları üretir.
      4. Tip kontrolü + lint çalıştırır (isteğe bağlı atlanabilir).
      5. Testleri çalıştırır (isteğe bağlı atlanabilir).
      6. electron-vite ile derler.
      7. electron-builder ile NSIS installer üretir.

    Çıktı: dist/Uryx-Setup.exe, .sha256, latest.yml, .blockmap

.PARAMETER SkipTests
    Testleri atlar.

.PARAMETER SkipLint
    Tip kontrolü ve lint adımını atlar.

.PARAMETER DirOnly
    Installer üretmeden yalnızca paketlenmemiş klasör çıktısı alır (hızlı deneme).

.PARAMETER E2E
    vitest sonrası python scripts/e2e_product.py (Whisper/LLM yoksa atlar; VM yok).

.EXAMPLE
    .\scripts\build-windows.ps1

.EXAMPLE
    .\scripts\build-windows.ps1 -SkipTests -DirOnly
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipLint,
    [switch]$DirOnly,
    [switch]$E2E
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopDir = Join-Path $RepoRoot 'apps\desktop'
$DistDir = Join-Path $RepoRoot 'dist'
Set-Location $RepoRoot

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok { param([string]$Text) Write-Host "  [OK]   $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  [UYARI] $Text" -ForegroundColor Yellow }
function Write-Err { param([string]$Text) Write-Host "  [HATA] $Text" -ForegroundColor Red }
function Write-Info { param([string]$Text) Write-Host "         $Text" -ForegroundColor DarkGray }

function Stop-WithError {
    param([string]$Message, [string[]]$Hints = @())
    Write-Err $Message
    foreach ($hint in $Hints) { Write-Info "-> $hint" }
    Write-Host ''
    exit 1
}

Write-Host ''
Write-Host '  ╔═══════════════════════════════════════════════╗' -ForegroundColor Blue
Write-Host '  ║   URYX   ·  Windows installer üretimi        ║' -ForegroundColor Blue
Write-Host '  ╚═══════════════════════════════════════════════╝' -ForegroundColor Blue

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Write-Step 'Ortam doğrulanıyor'

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Stop-WithError 'Node.js bulunamadı.' @('https://nodejs.org adresinden Node.js 20+ kurun.')
}
$nodeMajor = [int]((node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 20) {
    Stop-WithError "Node.js sürümü çok eski ($(node --version))." @('En az Node.js 20 gerekli.')
}
Write-Ok "Node.js $(node --version)"
Write-Ok "npm $(npm --version)"

Write-Step 'Bağımlılıklar kuruluyor'

if (-not (Test-Path (Join-Path $RepoRoot 'node_modules'))) {
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'npm install başarısız.' }
    Write-Ok 'Bağımlılıklar kuruldu'
}
else {
    Write-Ok 'node_modules mevcut'
}

Write-Step 'İkonlar üretiliyor'
node (Join-Path $RepoRoot 'scripts\generate-icons.mjs')
if ($LASTEXITCODE -ne 0) { Stop-WithError 'İkon üretimi başarısız.' }

if (-not $SkipLint) {
    Write-Step 'Tip kontrolü çalıştırılıyor'
    npm run typecheck --workspace @uryx/desktop
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'Tip kontrolü başarısız.' @(
            'Hataları düzeltin veya -SkipLint ile atlayın (önerilmez).'
        )
    }
    Write-Ok 'Tip kontrolü temiz'

    Write-Step 'Lint çalıştırılıyor'
    npm run lint
    if ($LASTEXITCODE -ne 0) {
        Write-Warn 'Lint uyarıları var; derlemeye devam ediliyor.'
    }
    else {
        Write-Ok 'Lint temiz'
    }
}
else {
    Write-Warn 'Tip kontrolü ve lint atlandı.'
}

if (-not $SkipTests) {
    Write-Step 'Testler çalıştırılıyor'
    npm run test --workspace @uryx/desktop
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'Testler başarısız.' @('Hataları düzeltin veya -SkipTests ile atlayın.')
    }
    Write-Ok 'Testler geçti'
}
else {
    Write-Warn 'Testler atlandı.'
}

if ($E2E) {
    Write-Step 'Ürün E2E (scripts/e2e_product.py; tarayıcı tıklama yok)'
    python (Join-Path $RepoRoot 'scripts\e2e_product.py')
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'Ürün E2E başarısız.' @('Whisper/LLM kapalıysa işler atlanır; gerçek hata yukarıda.')
    }
    Write-Ok 'E2E bitti'
}

Write-Step 'Uygulama derleniyor (electron-vite)'

Push-Location $DesktopDir
try {
    foreach ($dir in @('out', 'release', 'release-pack')) {
        $path = Join-Path $DesktopDir $dir
        if (-not (Test-Path $path)) { continue }
        try {
            Remove-Item $path -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warn "Eski çıktı kilitli, atlanıyor: $dir ($($_.Exception.Message))"
        }
    }

    npx electron-vite build
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'electron-vite build başarısız.' }
    Write-Ok 'Derleme tamamlandı'

    Write-Step $(if ($DirOnly) { 'Paketleniyor (installer üretilmeyecek)' } else { 'Windows installer üretiliyor' })

    $builderArgs = @('electron-builder', '--win', '--config', 'electron-builder.yml')
    if ($DirOnly) { $builderArgs += '--dir' }

    $script:UryxReleaseDirName = 'release'
    $lockedAsar = Join-Path $DesktopDir 'release\win-unpacked\resources\app.asar'
    if (Test-Path $lockedAsar) {
        try {
            [IO.File]::Open($lockedAsar, 'Open', 'ReadWrite', 'None').Dispose()
        }
        catch {
            $script:UryxReleaseDirName = 'release-pack'
            $builderArgs += '-c.directories.output=release-pack'
            Write-Warn 'Eski release/ kilitli; çıktı release-pack/ altına yazılıyor.'
        }
    }

    npx @builderArgs
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'electron-builder başarısız.' @(
            'Antivirüs yazılımı NSIS derlemesini engelliyor olabilir.',
            'release/ klasörünü silip tekrar deneyin.'
        )
    }
}
finally {
    Pop-Location
}

Write-Step 'Çıktı hazırlanıyor'

$releaseDir = Join-Path $DesktopDir $(if ($script:UryxReleaseDirName) { $script:UryxReleaseDirName } else { 'release' })
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$installer = Get-ChildItem -Path $releaseDir -Filter '*.exe' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*Setup*' } |
    Select-Object -First 1

if ($installer) {
    $target = Join-Path $DistDir 'Uryx-Setup.exe'
    Copy-Item $installer.FullName $target -Force
    $sizeMb = [math]::Round($installer.Length / 1MB, 1)

    Write-Ok "Installer hazır: dist\Uryx-Setup.exe ($sizeMb MB)"

    $hash = (Get-FileHash $target -Algorithm SHA256).Hash
    Set-Content -Path (Join-Path $DistDir 'Uryx-Setup.exe.sha256') -Value $hash -Encoding utf8
    Write-Info "SHA256: $hash"

    $latestYml = Join-Path $releaseDir 'latest.yml'
    $blockmap = Join-Path $releaseDir 'Uryx-Setup.exe.blockmap'
    if (-not (Test-Path $latestYml) -or -not (Test-Path $blockmap)) {
        Stop-WithError 'electron-updater dosyaları eksik (latest.yml / .blockmap).' @(
            'electron-builder NSIS çıktısında bu dosyalar üretilmeli.',
            'GitHub Release''e yalnızca Uryx-Setup.exe yüklemeyin; otomatik güncelleme kırılır.',
            'Yayın için: .\scripts\publish-github-release.ps1 -Tag vX.Y.Z'
        )
    }
    Copy-Item $latestYml (Join-Path $DistDir 'latest.yml') -Force
    Copy-Item $blockmap (Join-Path $DistDir 'Uryx-Setup.exe.blockmap') -Force
    Write-Ok 'Güncelleme manifesti kopyalandı: dist\latest.yml + dist\Uryx-Setup.exe.blockmap'

    $hasPfx = -not [string]::IsNullOrWhiteSpace($env:WIN_CSC_LINK) -or
        -not [string]::IsNullOrWhiteSpace($env:CSC_LINK)
    $hasAzure =
        -not [string]::IsNullOrWhiteSpace($env:AZURE_TENANT_ID) -and
        -not [string]::IsNullOrWhiteSpace($env:AZURE_CLIENT_ID) -and
        -not [string]::IsNullOrWhiteSpace($env:AZURE_CLIENT_SECRET) -and
        (-not [string]::IsNullOrWhiteSpace($env:AZURE_CODE_SIGNING_ACCOUNT_NAME) -or
         -not [string]::IsNullOrWhiteSpace($env:AZURE_TRUSTED_SIGNING_ACCOUNT)) -and
        (-not [string]::IsNullOrWhiteSpace($env:AZURE_CERT_PROFILE_NAME) -or
         -not [string]::IsNullOrWhiteSpace($env:AZURE_CERTIFICATE_PROFILE_NAME))
    if ($hasPfx -or $hasAzure) {
        $signtool = Get-Command signtool -ErrorAction SilentlyContinue
        if (-not $signtool) {
            Write-Warn 'signtool yok — Authenticode doğrulanamadı.'
        }
        else {
            & signtool verify /pa $target
            if ($LASTEXITCODE -ne 0) {
                Stop-WithError 'Authenticode doğrulaması başarısız (signtool /pa).' @(
                    'Self-signed “imzalı” değildir.',
                    'OV .pfx: WIN_CSC_LINK + WIN_CSC_KEY_PASSWORD'
                )
            }
            Write-Ok 'Authenticode doğrulandı (signtool /pa).'
        }
    }
    else {
        Write-Warn 'Authenticode yok — installer imzasız. Self-signed üretmeyin; imzasızı imzalı demeyin.'
    }
}
elseif ($DirOnly) {
    Write-Ok "Paketlenmiş klasör: $releaseDir\win-unpacked"
}
else {
    Write-Warn 'Installer dosyası bulunamadı. release/ klasörünü kontrol edin.'
}

$stopwatch.Stop()
Write-Host ''
Write-Host "  Tamamlandı · $([math]::Round($stopwatch.Elapsed.TotalMinutes, 1)) dakika" -ForegroundColor Green
Write-Host ''
Write-Info 'Kurulumdan sonra Docker servislerini başlatmayı unutmayın:'
Write-Info '  docker compose up -d'
Write-Host ''
