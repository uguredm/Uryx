# Yerel Modeller (GGUF)

llama.cpp (`llm` servisi) GGUF ağırlıklarını **ortak kullanıcı kökünden** okur:

`%LOCALAPPDATA%\Uryx\models`

Installer ve `.\scripts\start-dev.ps1` aynı dizine bakar. Compose:

`LLM_MODELS_DIR` → container `/models` (boşsa `./models`).

## Kalite (taze kurulum varsayılanı)

| Dosya | Kaynak | Boyut |
|---|---|---|
| `Qwen3-8B-Q4_K_M.gguf` | [unsloth/Qwen3-8B-GGUF](https://huggingface.co/unsloth/Qwen3-8B-GGUF) | ~5 GB |

## Dengeli

| Dosya | Kaynak | Boyut |
|---|---|---|
| `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | [unsloth/Qwen3-4B-Instruct-2507-GGUF](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF) | ~2.5 GB |

## Hızlı / zayıf GPU

| Dosya | Kaynak | Boyut |
|---|---|---|
| `Qwen3-1.7B-Q4_K_M.gguf` | [unsloth/Qwen3-1.7B-GGUF](https://huggingface.co/unsloth/Qwen3-1.7B-GGUF) | ~1.1 GB |

Ayarlar’daki preset kartı `.env` (`LLM_MODEL` / `LLM_GGUF_FILE`) yazar ve `llm` konteynerini yeniden yükler.

```powershell
.\scripts\pull-llm-gguf.ps1
# 4B-Instruct-2507:
.\scripts\pull-llm-gguf.ps1 -Repo unsloth/Qwen3-4B-Instruct-2507-GGUF -File Qwen3-4B-Instruct-2507-Q4_K_M.gguf
# 1.7B:
.\scripts\pull-llm-gguf.ps1 -Repo unsloth/Qwen3-1.7B-GGUF -File Qwen3-1.7B-Q4_K_M.gguf
docker compose up -d llm
```

`.env` eşlemesi (8B):

- `LLM_MODELS_DIR=%LOCALAPPDATA%/Uryx/models` (ileri eğik çizgi)
- `LLM_GGUF_FILE=Qwen3-8B-Q4_K_M.gguf`
- `LLM_MODEL=qwen3-8b`

Bu klasördeki README git’tedir; GGUF dosyaları git’e eklenmez.
