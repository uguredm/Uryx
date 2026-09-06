<#
.SYNOPSIS
    Uryx geliştirme ortamını tek komutla başlatır.

.DESCRIPTION
    Sırasıyla:
      1. Docker Desktop çalışıyor mu kontrol eder.
      2. NVIDIA GPU erişimini kontrol eder.
      3. .env dosyasını kontrol eder (yoksa .env.example'dan oluşturur).
      4. Node bağımlılıklarını kurar (eksikse).
      5. Backend servislerini başlatır.
      6. Healthcheck sonuçlarını bekler.
      7. Electron uygulamasını başlatır.
      8. Hata varsa anlaşılır şekilde gösterir.

.PARAMETER SkipDocker
    Docker servislerini başlatmaz; yalnızca Electron'u açar.

.PARAMETER SkipGpu
    GPU kontrolünü atlar (CPU-only kurulumlar için).

.PARAMETER NoLlm
    llama.cpp (llm) servisini başlatmaz. GPU yoksa veya GGUF indirilmediyse
    kullanışlıdır; sohbet dışındaki tüm ekranlar çalışır.

.PARAMETER Timeout
    Healthcheck bekleme süresi (saniye). Varsayılan: 180.

.EXAMPLE
    .\scripts\start-dev.ps1

.EXAMPLE
    .\scripts\start-dev.ps1 -NoLlm -SkipGpu
#>
[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$SkipGpu,
    [switch]$NoLlm,
    [int]$Timeout = 180
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok { param([string]$Text) Write-Host "  [OK]   $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  [UYARI] $Text" -ForegroundColor Yellow }
function Write-Err { param([string]$Text) Write-Host "  [HATA] $Text" -ForegroundColor Red }
function Write-Info { param([string]$Text) Write-Host "         $Text" -ForegroundColor DarkGray }

function Test-Command {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Stop-WithError {
    param([string]$Message, [string[]]$Hints = @())
    Write-Err $Message
    foreach ($hint in $Hints) { Write-Info "-> $hint" }
    Write-Host ''
    exit 1
}

Write-Host ''
Write-Host '  ╔═══════════════════════════════════════════════╗' -ForegroundColor Blue
Write-Host '  ║   URYX  ·  yerel yapay zeka asistani        ║' -ForegroundColor Blue
Write-Host '  ╚═══════════════════════════════════════════════╝' -ForegroundColor Blue

Write-Step 'Gerekli araçlar kontrol ediliyor'

if (-not (Test-Command 'node')) {
    Stop-WithError 'Node.js bulunamadı.' @('https://nodejs.org adresinden Node.js 20+ kurun.')
}
$nodeVersion = (node --version).TrimStart('v')
$nodeMajor = [int]($nodeVersion.Split('.')[0])
if ($nodeMajor -lt 20) {
    Stop-WithError "Node.js $nodeVersion çok eski." @('En az Node.js 20 gerekli.')
}
Write-Ok "Node.js $nodeVersion"

if (-not (Test-Command 'npm')) {
    Stop-WithError 'npm bulunamadı.' @('Node.js kurulumunu tamamlayın.')
}
Write-Ok "npm $(npm --version)"

if (-not $SkipDocker) {
    Write-Step 'Docker Desktop kontrol ediliyor'

    if (-not (Test-Command 'docker')) {
        Stop-WithError 'Docker bulunamadı.' @(
            'Docker Desktop kurun: https://www.docker.com/products/docker-desktop',
            'Kurulumdan sonra WSL2 arka ucunu etkinleştirin.'
        )
    }

    docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
    if (-not $?) {
        Stop-WithError 'Docker Desktop çalışmıyor.' @(
            'Docker Desktop uygulamasını başlatın ve tamamen açılmasını bekleyin.',
            'Ardından bu scripti tekrar çalıştırın.'
        )
    }
    Write-Ok "Docker $(docker version --format '{{.Server.Version}}') çalışıyor"

    docker compose version --short 2>&1 | Out-Null
    if (-not $?) {
        Stop-WithError 'docker compose eklentisi bulunamadı.' @('Docker Desktop''ı güncelleyin.')
    }
    Write-Ok "docker compose $(docker compose version --short)"
}

$gpuAvailable = $false
if (-not $SkipGpu) {
    Write-Step 'NVIDIA GPU kontrol ediliyor'

    if (Test-Command 'nvidia-smi') {
        $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1)
        if ($gpuName) {
            $vram = (nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
            Write-Ok "$($gpuName.Trim()) · $([math]::Round([int]$vram / 1024, 1)) GB VRAM"
            $gpuAvailable = $true
            $vramGb = [math]::Round([int]$vram / 1024, 1)
            Write-Info 'Varsayılan Qwen3-8B Q4 + 8K ctx 12 GB kartta tam offload. 14B/27B yok.'
            if ([int]$vram -lt 10000) {
                Write-Warn "VRAM $vramGb GB — 8B sıkışabilir; Ayarlar'da 1.7B (fast) veya -NoLlm kullanın."
            }
        }
    }

    if (-not $gpuAvailable) {
        Write-Warn 'NVIDIA GPU bulunamadı.'
        Write-Info 'llm (llama.cpp) GPU olmadan başlamaz; Whisper varsayılanı CPU.'
        Write-Info 'CPU-only çalıştırmak için: .\scripts\start-dev.ps1 -NoLlm'
    }
    elseif (-not $SkipDocker) {
        docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L 2>&1 | Out-Null
        if ($?) {
            Write-Ok 'Docker konteynerlerinden GPU erişimi doğrulandı'
        }
        else {
            Write-Warn 'Docker konteynerleri GPU''ya erişemiyor.'
            Write-Info 'Docker Desktop > Settings > Resources > WSL Integration ayarlarını kontrol edin.'
            Write-Info 'NVIDIA Container Toolkit''in kurulu olduğundan emin olun.'
        }
    }
}

Write-Step '.env dosyası kontrol ediliyor'

$envPath = Join-Path $RepoRoot '.env'
$envExample = Join-Path $RepoRoot '.env.example'

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $envExample)) {
        Stop-WithError '.env.example bulunamadı. Depo eksik indirilmiş olabilir.'
    }
    Copy-Item $envExample $envPath
    Write-Ok '.env dosyası .env.example''dan oluşturuldu'

    $token = [guid]::NewGuid().ToString('N')
    (Get-Content $envPath -Raw) -replace 'URYX_LOCAL_TOKEN=\s*(\r?\n)', "URYX_LOCAL_TOKEN=$token`$1" |
        Set-Content $envPath -Encoding utf8 -NoNewline
    Write-Ok 'Yerel güvenlik token''ı üretildi'
    Write-Info "Token: $token"
    Write-Info 'Bu değeri Uryx > Ayarlar > Bağlantı > Yerel token alanına girin.'
}
else {
    Write-Ok '.env mevcut'
    $tokenLine = Select-String -Path $envPath -Pattern '^URYX_LOCAL_TOKEN=(.+)$' | Select-Object -First 1
    if (-not $tokenLine) {
        $tokenLine = Select-String -Path $envPath -Pattern '^JARVIS_LOCAL_TOKEN=(.+)$' | Select-Object -First 1
    }
    if ($tokenLine) {
        Write-Info "Yerel token tanımlı (Ayarlar ekranına girilmeli)."
    }
    else {
        Write-Warn 'URYX_LOCAL_TOKEN boş — kimlik doğrulama devre dışı (yalnızca geliştirme için uygundur).'
    }
}

Write-Step 'Node bağımlılıkları kontrol ediliyor'

if (-not (Test-Path (Join-Path $RepoRoot 'node_modules'))) {
    Write-Info 'npm install çalıştırılıyor (ilk kurulum birkaç dakika sürebilir)…'
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'npm install başarısız oldu.' @('Yukarıdaki hata mesajını inceleyin.')
    }
    Write-Ok 'Bağımlılıklar kuruldu'
}
else {
    Write-Ok 'node_modules mevcut'
}

if (-not (Test-Path (Join-Path $RepoRoot 'apps\desktop\build\icon.png'))) {
    node (Join-Path $RepoRoot 'scripts\generate-icons.mjs') | Out-Null
    Write-Ok 'Uygulama ikonları üretildi'
}

if (-not $SkipDocker) {
    Write-Step 'Backend servisleri başlatılıyor'

    $services = @('postgres', 'qdrant', 'uryx-api', 'tts', 'whisper')
    if (-not $NoLlm -and $gpuAvailable) {
        $ggufName = 'Qwen3-8B-Q4_K_M.gguf'
        $ggufLine = Select-String -Path $envPath -Pattern '^\s*LLM_GGUF_FILE=(.+)$' | Select-Object -First 1
        if ($ggufLine) {
            $ggufName = $ggufLine.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
        }
        $modelsDir = Join-Path $env:LOCALAPPDATA 'Uryx\models'
        $modelsLine = Select-String -Path $envPath -Pattern '^\s*LLM_MODELS_DIR=(.+)$' | Select-Object -First 1
        if ($modelsLine) {
            $parsed = $modelsLine.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
            if ($parsed) { $modelsDir = $parsed }
        }
        if ($env:LLM_MODELS_DIR) { $modelsDir = $env:LLM_MODELS_DIR }
        $env:LLM_MODELS_DIR = $modelsDir.Replace('\', '/')
        $ggufPath = Join-Path $modelsDir $ggufName
        $legacyGguf = Join-Path $RepoRoot "models\$ggufName"
        if (-not (Test-Path $ggufPath) -and (Test-Path $legacyGguf)) {
            New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
            Copy-Item -LiteralPath $legacyGguf -Destination $ggufPath -Force
            Write-Info "GGUF kullanıcı dizinine kopyalandı: $ggufPath"
        }
        if (-not (Test-Path $ggufPath)) {
            Write-Warn "GGUF yok: $ggufPath"
            Write-Info 'İndirin: .\scripts\pull-llm-gguf.ps1  (llm yine de başlatılacak; dosya yoksa container hata verir)'
        }
        $services += 'llm'
    }
    elseif (-not $NoLlm) { Write-Warn 'GPU bulunamadığı için llm (llama.cpp) atlanıyor (-NoLlm gibi davranılıyor).' }

    Write-Info "Servisler: $($services -join ', ')"
    Write-Info 'İlk çalıştırmada imajlar indirilir/derlenir; bu işlem uzun sürebilir.'

    docker compose up -d @services
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'docker compose up başarısız oldu.' @(
            'Log için: docker compose logs --tail=100',
            'Port çakışması varsa .env içindeki port değerlerini değiştirin.'
        )
    }
    Write-Ok 'Konteynerler başlatıldı'

    Write-Step 'Servislerin hazır olması bekleniyor'

    $apiPort = 8080
    $portLine = Select-String -Path $envPath -Pattern '^URYX_API_PORT=(\d+)' | Select-Object -First 1
    if (-not $portLine) {
        $portLine = Select-String -Path $envPath -Pattern '^JARVIS_API_PORT=(\d+)' | Select-Object -First 1
    }
    if ($portLine) { $apiPort = [int]$portLine.Matches[0].Groups[1].Value }

    $healthUrl = "http://127.0.0.1:$apiPort/health"
    $deadline = (Get-Date).AddSeconds($Timeout)
    $ready = $false
    $spinner = @('|', '/', '-', '\')
    $tick = 0

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
            $ready = $true
            Write-Host "`r" -NoNewline
            Write-Ok "uryx-api hazır (durum: $($response.status))"

            foreach ($key in $response.services.PSObject.Properties.Name) {
                $state = $response.services.$key
                if ($state -eq 'up') { Write-Ok "$key" }
                elseif ($state -eq 'starting') { Write-Warn "$key başlatılıyor…" }
                else { Write-Warn "$key kapalı" }
            }
            break
        }
        catch {
            $tick++
            Write-Host "`r  $($spinner[$tick % 4]) uryx-api bekleniyor… ($([int]($deadline - (Get-Date)).TotalSeconds)s)" -NoNewline -ForegroundColor DarkGray
            Start-Sleep -Milliseconds 1200
        }
    }

    Write-Host "`r$(' ' * 60)`r" -NoNewline

    if (-not $ready) {
        Write-Err "uryx-api $Timeout saniye içinde hazır olmadı."
        Write-Info 'Son loglar:'
        docker compose logs --tail=30 uryx-api
        Write-Info ''
        Write-Info 'Uygulama yine de açılacak; Sistem Durumu ekranından servisleri izleyebilirsiniz.'
    }

    if (-not $NoLlm -and $gpuAvailable) {
        Write-Info 'llama-server GGUF yüklüyor — models/ altında dosya yoksa önce: .\scripts\pull-llm-gguf.ps1'
        Write-Info 'İlerlemeyi izlemek için: docker compose logs -f llm'
    }
}

Write-Step 'Uryx masaüstü uygulaması başlatılıyor'
Write-Info 'Kapatmak için bu pencerede Ctrl+C tuşlarına basın.'
Write-Host ''

$env:URYX_REPO_ROOT = $RepoRoot
if (-not $env:JARVIS_REPO_ROOT) { $env:JARVIS_REPO_ROOT = $RepoRoot }
npm run dev

if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    Write-Host ''
    Stop-WithError "Electron uygulaması hata ile kapandı (çıkış kodu: $LASTEXITCODE)." @(
        'Bağımlılıkları yeniden kurmayı deneyin: npm install',
        'Ayrıntılı hata için yukarıdaki çıktıyı inceleyin.'
    )
}
