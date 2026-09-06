<#
.SYNOPSIS
    Unsloth Qwen3 GGUF dosyasını %LOCALAPPDATA%\Uryx\models altına indirir.

.DESCRIPTION
    Varsayılan: unsloth/Qwen3-8B-GGUF → Qwen3-8B-Q4_K_M.gguf (~5 GB).
    Installer ve geliştirme aynı köke bakar (LLM_MODELS_DIR).
    Hugging Face CLI (hf) veya Python huggingface_hub kullanır.
    Dosya zaten varsa atlar (-Force ile yeniden indirir).

.PARAMETER Repo
    Hugging Face repo id. Varsayılan: unsloth/Qwen3-8B-GGUF

.PARAMETER File
    İndirilecek GGUF dosya adı. Varsayılan: Qwen3-8B-Q4_K_M.gguf
    (.env içindeki LLM_GGUF_FILE ile aynı olmalı)

.PARAMETER Force
    Mevcut dosyayı silip yeniden indirir.

.EXAMPLE
    .\scripts\pull-llm-gguf.ps1

.EXAMPLE
    .\scripts\pull-llm-gguf.ps1 -Repo unsloth/Qwen3-4B-Instruct-2507-GGUF -File Qwen3-4B-Instruct-2507-Q4_K_M.gguf

.EXAMPLE
    .\scripts\pull-llm-gguf.ps1 -Repo unsloth/Qwen3-1.7B-GGUF -File Qwen3-1.7B-Q4_K_M.gguf
#>
[CmdletBinding()]
param(
    [string]$Repo = 'unsloth/Qwen3-8B-GGUF',
    [string]$File = 'Qwen3-8B-Q4_K_M.gguf',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Get-UryxModelsDir {
    $fromEnv = [string]$env:LLM_MODELS_DIR
    if ($fromEnv.Trim()) { return $fromEnv.Trim() }
    $envPath = Join-Path $RepoRoot '.env'
    if (Test-Path $envPath) {
        $line = Select-String -Path $envPath -Pattern '^\s*LLM_MODELS_DIR=(.+)$' | Select-Object -First 1
        if ($line) {
            $value = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
            if ($value) { return $value }
        }
    }
    return (Join-Path $env:LOCALAPPDATA 'Uryx\models')
}

function Set-DotEnvKey([string]$Key, [string]$Value) {
    $envPath = Join-Path $RepoRoot '.env'
    if (-not (Test-Path $envPath)) { return }
    $content = Get-Content -LiteralPath $envPath -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { return }
    $line = "$Key=$Value"
    if ($content -match "(?m)^$Key=.*$") {
        $content = [regex]::Replace($content, "(?m)^$Key=.*$", $line)
    }
    else {
        $content = $content.TrimEnd() + "`r`n$line`r`n"
    }
    Set-Content -LiteralPath $envPath -Value $content -Encoding utf8 -NoNewline
}

$ModelsDir = Get-UryxModelsDir
$Target = Join-Path $ModelsDir $File
$env:LLM_MODELS_DIR = $ModelsDir.Replace('\', '/')

Write-Host ''
Write-Host '  Uryx — GGUF indirme' -ForegroundColor Cyan
Write-Host "  Repo : $Repo"
Write-Host "  Dosya: $File"
Write-Host "  Hedef: $Target"
Write-Host ''

if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir | Out-Null
}

if ((Test-Path $Target) -and -not $Force) {
    $sizeGb = [math]::Round((Get-Item $Target).Length / 1GB, 2)
    Write-Host "  Dosya zaten var (${sizeGb} GB). Atlamak için -Force kullanın." -ForegroundColor Green
    Write-Host "  Sonraki adım: docker compose up -d llm"
    Write-Host ''
    exit 0
}

if ((Test-Path $Target) -and $Force) {
    Remove-Item -Force $Target
}

$token = $env:HUGGING_FACE_HUB_TOKEN
if (-not $token -and (Test-Path (Join-Path $RepoRoot '.env'))) {
    $line = Select-String -Path (Join-Path $RepoRoot '.env') -Pattern '^\s*HUGGING_FACE_HUB_TOKEN=(.+)$' |
        Select-Object -First 1
    if ($line) {
        $token = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
        if ($token) { $env:HUGGING_FACE_HUB_TOKEN = $token }
    }
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$downloaded = $false

if (-not $downloaded -and (Test-Command 'hf')) {
    Write-Host '  Yöntem: hf download' -ForegroundColor DarkGray
    & hf download $Repo --include $File --local-dir $ModelsDir
    if ($LASTEXITCODE -eq 0 -and (Test-Path $Target)) { $downloaded = $true }
    else {
        $nested = Get-ChildItem -Path $ModelsDir -Recurse -Filter $File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($nested -and $nested.FullName -ne $Target) {
            Move-Item -Force $nested.FullName $Target
            $downloaded = Test-Path $Target
        }
    }
}

if (-not $downloaded -and (Test-Command 'python')) {
    Write-Host '  Yöntem: python huggingface_hub' -ForegroundColor DarkGray
    $py = @"
import sys
from pathlib import Path
try:
    from huggingface_hub import hf_hub_download
except ImportError:
    print('huggingface_hub yok; pip install huggingface_hub', file=sys.stderr)
    sys.exit(2)
path = hf_hub_download(
    repo_id='$Repo',
    filename='$File',
    local_dir=r'$ModelsDir',
    local_dir_use_symlinks=False,
)
dest = Path(r'$Target')
src = Path(path)
if src.resolve() != dest.resolve():
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src.replace(dest)
print(dest)
"@
    $tmp = Join-Path $env:TEMP "uryx-pull-gguf-$PID.py"
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    try {
        & python $tmp
        if ($LASTEXITCODE -eq 0 -and (Test-Path $Target)) { $downloaded = $true }
    }
    finally {
        Remove-Item -Force $tmp -ErrorAction SilentlyContinue
    }
}

if (-not $downloaded) {
    Write-Host ''
    Write-Host '  İndirme başarısız.' -ForegroundColor Red
    Write-Host '  Kurulum seçenekleri:'
    Write-Host '    pip install -U "huggingface_hub[cli]"'
    Write-Host "    hf download $Repo --include $File --local-dir models"
    Write-Host '  Gated dosya için HUGGING_FACE_HUB_TOKEN ayarlayın.'
    Write-Host ''
    exit 1
}

$sizeGb = [math]::Round((Get-Item $Target).Length / 1GB, 2)
Write-Host ''
Write-Host "  Tamam (${sizeGb} GB)." -ForegroundColor Green
Write-Host "  .env: LLM_GGUF_FILE=$File"
Write-Host "  .env: LLM_MODELS_DIR=$($env:LLM_MODELS_DIR)"
Set-DotEnvKey 'LLM_MODELS_DIR' $env:LLM_MODELS_DIR
Set-DotEnvKey 'LLM_GGUF_FILE' $File
if ($File -match '14B|27B|32B') {
    Write-Host '  Uyarı: 14B/27B 12 GB kartta önerilmez (CPU spill).' -ForegroundColor Yellow
}
elseif ($File -match '8B|9B') {
    $vramMb = 0
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $vramMb = [int]((nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1))
    }
    if ($vramMb -gt 0 -and $vramMb -lt 10000) {
        Write-Host "  Uyarı: 8B Q4 + 8K ctx için ~12 GB VRAM önerilir (görülen: $vramMb MB)." -ForegroundColor Yellow
    }
}
Write-Host '  Başlat: docker compose up -d llm'
Write-Host '  Log   : docker compose logs -f llm'
Write-Host ''
