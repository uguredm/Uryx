"""Yirmi Türkçe RAG nDCG çifti — Signal vs BGE karşılaştırması için."""

from __future__ import annotations

from typing import Any

NDCG_CASES: list[dict[str, Any]] = [
    {
        "query": "RTX 5070 ekran kartım kaç GB VRAM",
        "docs": [
            {"id": "r1", "content": "Kullanıcının ekran kartı NVIDIA RTX 5070, 12 GB VRAM.", "fused_score": 0.2},
            {"id": "r2", "content": "Docker Desktop WSL2 arka planda çalışır.", "fused_score": 0.4},
            {"id": "r3", "content": "Piper Türkçe ses modeli dfki-medium.", "fused_score": 0.3},
            {"id": "r4", "content": "Qdrant cosine benzerlik 384 boyutta.", "fused_score": 0.35},
            {"id": "r5", "content": "Outlook takvim COM ile salt okunur.", "fused_score": 0.1},
        ],
        "relevance": {"r1": 3, "r2": 0, "r3": 0, "r4": 0, "r5": 0},
    },
    {
        "query": "projelerimi hangi klasörde tutuyorum",
        "docs": [
            {"id": "p1", "content": "Kullanıcı projelerini Masaüstü/Uryx klasöründe tutuyor.", "fused_score": 0.15},
            {"id": "p2", "content": "llama.cpp 8K bağlam kullanır.", "fused_score": 0.5},
            {"id": "p3", "content": "Whisper varsayılanı CPU medium.", "fused_score": 0.4},
            {"id": "p4", "content": "NSIS kurucu Uryx-Setup.exe üretir.", "fused_score": 0.2},
        ],
        "relevance": {"p1": 3, "p2": 0, "p3": 0, "p4": 0},
    },
    {
        "query": "yerel model adı ne quality preset",
        "docs": [
            {"id": "m1", "content": "Taze kurulum varsayılanı quality: Qwen3-8B Q4_K_M.", "fused_score": 0.25},
            {"id": "m2", "content": "fast preset 1.7B hızlı deneme içindir.", "fused_score": 0.45},
            {"id": "m3", "content": "balanced 4B-Instruct-2507 non-thinking.", "fused_score": 0.4},
            {"id": "m4", "content": "Kokoro Türkçe konuşmaz.", "fused_score": 0.3},
        ],
        "relevance": {"m1": 3, "m2": 1, "m3": 1, "m4": 0},
    },
    {
        "query": "taranmış PDF nasıl indekslenir",
        "docs": [
            {"id": "o1", "content": "Metinsiz PDF sayfalarında RapidOCR ONNX çalışır, Tesseract yok.", "fused_score": 0.2},
            {"id": "o2", "content": "Chrome'u open_application ile aç.", "fused_score": 0.5},
            {"id": "o3", "content": "nDCG rerank kalitesini ölçer.", "fused_score": 0.3},
            {"id": "o4", "content": "Piper dfki Türkçe yedek TTS.", "fused_score": 0.25},
        ],
        "relevance": {"o1": 3, "o2": 0, "o3": 1, "o4": 0},
    },
    {
        "query": "otomatik güncelleme latest.yml nerede",
        "docs": [
            {"id": "u1", "content": "GitHub Release'te latest.yml + Uryx-Setup.exe + blockmap zorunlu.", "fused_score": 0.22},
            {"id": "u2", "content": "electron-builder --publish kullanma.", "fused_score": 0.18},
            {"id": "u3", "content": "Hava durumu Open-Meteo weather aracı.", "fused_score": 0.4},
            {"id": "u4", "content": "Qdrant volume jarvis-qdrant-data.", "fused_score": 0.35},
        ],
        "relevance": {"u1": 3, "u2": 2, "u3": 0, "u4": 0},
    },
    {
        "query": "docker compose volume silinir mi",
        "docs": [
            {"id": "v1", "content": "docker compose down -v yasak; jarvis-*-data silinmez.", "fused_score": 0.2},
            {"id": "v2", "content": "Koleksiyon adları uryx_* kopyalanır, jarvis_* durur.", "fused_score": 0.25},
            {"id": "v3", "content": "Instagram tarayıcı oturumu elle açılır.", "fused_score": 0.45},
            {"id": "v4", "content": "calculate aracı birim çevirir.", "fused_score": 0.3},
        ],
        "relevance": {"v1": 3, "v2": 2, "v3": 0, "v4": 0},
    },
    {
        "query": "takvim etkinliklerini kim okur",
        "docs": [
            {"id": "c1", "content": "list_calendar_events Outlook COM HOST, Graph değil.", "fused_score": 0.15},
            {"id": "c2", "content": "görev listesi list_processes demektir, Outlook görev değil.", "fused_score": 0.2},
            {"id": "c3", "content": "Playwright click yasak.", "fused_score": 0.5},
            {"id": "c4", "content": "MiniLM embedding 384 CPU.", "fused_score": 0.4},
        ],
        "relevance": {"c1": 3, "c2": 2, "c3": 0, "c4": 0},
    },
    {
        "query": "tarayıcıda formu kim doldurur",
        "docs": [
            {"id": "b1", "content": "browser_fill_form MEDIUM onaylı native araç; Playwright click yok.", "fused_score": 0.2},
            {"id": "b2", "content": "browser_open sayfa açar, click bu dalda yok.", "fused_score": 0.25},
            {"id": "b3", "content": "wiki_lookup ansiklopedi içindir.", "fused_score": 0.45},
            {"id": "b4", "content": "Edge Neural TTS ağ üzerinden.", "fused_score": 0.3},
        ],
        "relevance": {"b1": 3, "b2": 2, "b3": 0, "b4": 0},
    },
    {
        "query": "uyandırma kelimesi whisper mı",
        "docs": [
            {"id": "w1", "content": "Hey Uryx için openWakeWord ONNX host; Whisper uyandırma motoru değil.", "fused_score": 0.2},
            {"id": "w2", "content": "Whisper STT komut metnini çözer.", "fused_score": 0.35},
            {"id": "w3", "content": "wakeWordEnabled varsayılan kapalı.", "fused_score": 0.3},
            {"id": "w4", "content": "Qwen3.5-9B deneysel agent preset.", "fused_score": 0.4},
        ],
        "relevance": {"w1": 3, "w2": 1, "w3": 2, "w4": 0},
    },
    {
        "query": "embedding modeli hangi boyut",
        "docs": [
            {"id": "e1", "content": "paraphrase-multilingual-MiniLM-L12-v2 384 boyut CPU.", "fused_score": 0.22},
            {"id": "e2", "content": "BGE-M3 1024 bu fazda yok.", "fused_score": 0.28},
            {"id": "e3", "content": "Hash fallback model indirilemezse devreye girer.", "fused_score": 0.25},
            {"id": "e4", "content": "Uryx-Setup.exe NSIS artifact adı.", "fused_score": 0.4},
        ],
        "relevance": {"e1": 3, "e2": 2, "e3": 2, "e4": 0},
    },
    {
        "query": "istanbul hava durumu hangi araç",
        "docs": [
            {"id": "h1", "content": "Hava ve sıcaklık için weather (Open-Meteo) kullanılır.", "fused_score": 0.2},
            {"id": "h2", "content": "air_quality AQI/PM içindir, hava tahmini değil.", "fused_score": 0.25},
            {"id": "h3", "content": "prayer_times namaz vakitleri.", "fused_score": 0.4},
            {"id": "h4", "content": "fx_rate döviz kuru.", "fused_score": 0.35},
        ],
        "relevance": {"h1": 3, "h2": 1, "h3": 0, "h4": 0},
    },
    {
        "query": "sohbet özeti nasıl yazılır",
        "docs": [
            {"id": "s1", "content": "index_episode summarize_turns ile LLM özetler; hata olursa compact_turns.", "fused_score": 0.2},
            {"id": "s2", "content": "MemoryEvaluator kalıcı fakt çıkarır, bölüm özeti değil.", "fused_score": 0.3},
            {"id": "s3", "content": "conversations vektör alanı aynı kalır.", "fused_score": 0.25},
            {"id": "s4", "content": "clipboard_read panoyu okur.", "fused_score": 0.45},
        ],
        "relevance": {"s1": 3, "s2": 1, "s3": 2, "s4": 0},
    },
    {
        "query": "rerank hangi model cpu",
        "docs": [
            {"id": "k1", "content": "BAAI/bge-reranker-v2-m3 CPU; yüklenemezse SignalReranker.", "fused_score": 0.18},
            {"id": "k2", "content": "Embedding MiniLM 384 değişmez.", "fused_score": 0.3},
            {"id": "k3", "content": "GPU 8B llama.cpp'ye ayrılır.", "fused_score": 0.22},
            {"id": "k4", "content": "ISS konumu iss_now aracı.", "fused_score": 0.4},
        ],
        "relevance": {"k1": 3, "k2": 2, "k3": 1, "k4": 0},
    },
    {
        "query": "public github'u kim açar",
        "docs": [
            {"id": "g1", "content": "Repo Public'i yalnızca kullanıcı açar; ajan visibility değiştirmez.", "fused_score": 0.2},
            {"id": "g2", "content": "publish.private true kalır ta ki kullanıcı açtım desin.", "fused_score": 0.25},
            {"id": "g3", "content": "dual-feed önce public latest.yml dener.", "fused_score": 0.28},
            {"id": "g4", "content": "npm_lookup paket arar.", "fused_score": 0.5},
        ],
        "relevance": {"g1": 3, "g2": 2, "g3": 1, "g4": 0},
    },
    {
        "query": "docker yoksa uygulama ne yapar",
        "docs": [
            {"id": "d1", "content": "Uryx resmi Docker Desktop kurucusunu indirir; kullanıcı UAC onaylar.", "fused_score": 0.2},
            {"id": "d2", "content": "NSIS paketine Docker gömülmez.", "fused_score": 0.25},
            {"id": "d3", "content": "start-dev.ps1 ürün yolu değildir.", "fused_score": 0.3},
            {"id": "d4", "content": "pypi_lookup Python paketi.", "fused_score": 0.45},
        ],
        "relevance": {"d1": 3, "d2": 2, "d3": 1, "d4": 0},
    },
    {
        "query": "adım ne senin ismin",
        "docs": [
            {"id": "n1", "content": "Asistanın adı Uryx. Jarvis deme.", "fused_score": 0.2},
            {"id": "n2", "content": "HUD markası URYX.", "fused_score": 0.35},
            {"id": "n3", "content": "GitHub uguredm/Uryx.", "fused_score": 0.3},
            {"id": "n4", "content": "iban_check IBAN doğrular.", "fused_score": 0.5},
        ],
        "relevance": {"n1": 3, "n2": 1, "n3": 1, "n4": 0},
    },
    {
        "query": "belge araması hybrid nasıl",
        "docs": [
            {"id": "x1", "content": "Dense Qdrant + sparse Postgres RRF sonra cross-encoder rerank.", "fused_score": 0.2},
            {"id": "x2", "content": "search_documents araç adı.", "fused_score": 0.25},
            {"id": "x3", "content": "MMR çeşitlilik için lambda 0.72.", "fused_score": 0.3},
            {"id": "x4", "content": "Spotify open_media_application.", "fused_score": 0.45},
        ],
        "relevance": {"x1": 3, "x2": 2, "x3": 1, "x4": 0},
    },
    {
        "query": "imza smartscreen için ne lazım",
        "docs": [
            {"id": "i1", "content": "Azure Trusted Signing veya OV; self-signed SmartScreen'e yaramaz.", "fused_score": 0.2},
            {"id": "i2", "content": "Faz 4 installer imzası.", "fused_score": 0.25},
            {"id": "i3", "content": "Piper yerel TTS yedeği.", "fused_score": 0.4},
            {"id": "i4", "content": "dns_lookup MX kaydı.", "fused_score": 0.35},
        ],
        "relevance": {"i1": 3, "i2": 2, "i3": 0, "i4": 0},
    },
    {
        "query": "kod dosyaları hangi collection",
        "docs": [
            {"id": "z1", "content": "Kod chunk'ları uryx_code (eski jarvis_code kopyası) 384 cosine.", "fused_score": 0.2},
            {"id": "z2", "content": "Belgeler uryx_documents.", "fused_score": 0.3},
            {"id": "z3", "content": "Hafıza uryx_memory kişiseldir, koda karışmaz.", "fused_score": 0.28},
            {"id": "z4", "content": "earthquakes deprem listesi.", "fused_score": 0.45},
        ],
        "relevance": {"z1": 3, "z2": 1, "z3": 1, "z4": 0},
    },
    {
        "query": "ses sentezi türkçe yerel yedek",
        "docs": [
            {"id": "t1", "content": "Türkçe yerel TTS yedeği Piper tr_TR-dfki-medium; Kokoro değil.", "fused_score": 0.2},
            {"id": "t2", "content": "Edge Ahmet neural kaliteli ağ sesi.", "fused_score": 0.3},
            {"id": "t3", "content": "XTTS yalnız ses klonu, v0.11 teslimi değil.", "fused_score": 0.25},
            {"id": "t4", "content": "postal_lookup posta kodu.", "fused_score": 0.4},
        ],
        "relevance": {"t1": 3, "t2": 1, "t3": 1, "t4": 0},
    },
    {
        "query": "araç onay modalı ne zaman çıkar",
        "docs": [
            {"id": "y1", "content": "Risk medium/high araçlar kullanıcı onay modalı ister.", "fused_score": 0.2},
            {"id": "y2", "content": "LOW host araçları sessiz çalışabilir.", "fused_score": 0.3},
            {"id": "y3", "content": "Model serbest kabuk alamaz.", "fused_score": 0.25},
            {"id": "y4", "content": "sun_times gün doğumu.", "fused_score": 0.45},
        ],
        "relevance": {"y1": 3, "y2": 1, "y3": 2, "y4": 0},
    },
]
