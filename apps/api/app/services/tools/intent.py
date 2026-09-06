"""Türkçe işlem niyeti — model beklemeden güvenilir araç yönlendirmesi.

Küçük yerel modeller (Qwen 4B/8B) "Chrome'u aç" / "şunu kopyala" gibi
net komutlarda 40+ şema arasında kaybolup anlatıya düşer. Web/Spotify
akışındaki gibi, günlük bilgisayar işleri için deterministik bir eşleme
üretilir; model serbest kabuk almaz, allowlist + risk + onay durur.

Kalıplar (uyarlama): Open Interpreter Computer API (seçili metin / ön plan),
Continue allow-ask-exclude (dar araç yüzeyi), OpenAI "description = when to use".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_APP_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bnot\s*defteri\b|\bnotepad\b"), "notepad"),
    (re.compile(r"\bhesap\s*makinesi\b|\bcalculator\b|\bcalc\b|\bhesap\b"), "calc"),
    (re.compile(r"\bdosya\s*gezgini\b|\bgezgin\b|\bexplorer\b"), "explorer"),
    (re.compile(r"\bpaint\b|\bpaint\.net\b"), "paint"),
    (re.compile(r"\bgoogle\s*chrome\b|\bchrome\b"), "chrome"),
    (re.compile(r"\bmicrosoft\s*edge\b|\bedge\b"), "edge"),
    (re.compile(r"\bfirefox\b"), "firefox"),
    (re.compile(r"\bvisual\s*studio\s*code\b|\bvs\s*code\b|\bvscode\b"), "vscode"),
    (re.compile(r"\bwindows\s*terminal\b|\bterminal\b|\bwt\b"), "terminal"),
    (
        re.compile(r"\bgörev\s*yöneticisi\b|\bgorev\s*yoneticisi\b|\btask\s*manager\b"),
        "task_manager",
    ),
    (re.compile(r"\bayarlar\b|\bsettings\b"), "settings"),
    (re.compile(r"\bkomut\s*istemi\b|\bcmd\b"), "cmd"),
    (re.compile(r"\bpowershell\b"), "powershell"),
    (re.compile(r"\bspotify\b"), "spotify"),
    (re.compile(r"\bsnipping\s*tool\b|\bkırpma\s*aracı\b"), "snippingtool"),
    (re.compile(r"\bwordpad\b"), "wordpad"),
)

_SPECIAL_FOLDERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"masaüst|masaust|desktop"), "desktop"),
    (re.compile(r"belgeler|documents"), "documents"),
    (re.compile(r"indirilen|downloads"), "downloads"),
    (re.compile(r"resimler|pictures"), "pictures"),
)
_LIST_HINT = re.compile(
    r"listele|içindekiler|icindekiler|dekileri|dekini\s+(göster|goster)|"
    r"kaç\s*dosya|kac\s*dosya|kaç\s*öğe|kac\s*oge"
)
_FILE_SEARCH_HINT = re.compile(
    r"\b(ara|bul|nerede|nelerde|dosya\s*ara|find)\b",
    re.IGNORECASE,
)
_CURRENCY = re.compile(
    r"\b(dolar|dollar|usd|euro|eur|sterlin|pound|gbp|tl|lira|try|"
    r"bitcoin|btc|ethereum|eth|kripto|kur|döviz|doviz)\b",
    re.IGNORECASE,
)
_CRYPTO = re.compile(r"\b(bitcoin|btc|ethereum|eth|kripto)\b", re.IGNORECASE)
_FIAT_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(dolar|dollar|usd)\b", re.I), "USD"),
    (re.compile(r"\b(euro|eur)\b", re.I), "EUR"),
    (re.compile(r"\b(sterlin|pound|gbp)\b", re.I), "GBP"),
    (re.compile(r"\b(yen|jpy)\b", re.I), "JPY"),
    (re.compile(r"\b(tl|lira|try)\b", re.I), "TRY"),
)
_APP_NOISE = frozenset(
    {
        "notepad",
        "not",
        "defteri",
        "hesap",
        "makinesi",
        "calculator",
        "calc",
        "gezgin",
        "explorer",
        "paint",
        "google",
        "chrome",
        "microsoft",
        "edge",
        "firefox",
        "visual",
        "studio",
        "code",
        "vscode",
        "windows",
        "terminal",
        "görev",
        "gorev",
        "yöneticisi",
        "yoneticisi",
        "task",
        "manager",
        "ayarlar",
        "settings",
        "komut",
        "istemi",
        "cmd",
        "powershell",
        "spotify",
        "snipping",
        "kırpma",
        "kirpma",
        "aracı",
        "araci",
        "wordpad",
        "uygulamasını",
        "uygulamasini",
        "uygulamayı",
        "uygulamayi",
        "uygulama",
        "programını",
        "programini",
        "programı",
        "programi",
        "program",
        "lütfen",
        "lutfen",
        "bana",
        "uryx",
        "hey",
    }
)
_UNIT_PAIR = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(km|kilometre|kilometer|m|metre|meter|cm|mm|mil|mile|miles|inch|inç|inc|"
    r"feet|foot|ayak|yard|kg|kilogram|g|gram|lb|lbs|pound|libre|oz|ons|"
    r"litre|liter|l|ml|galon|gallon|fahrenheit|santigrat|celsius|kelvin|"
    r"saat|dakika|saniye|mph|kmh)\s+"
    r"kaç\s+"
    r"(km|kilometre|kilometer|m|metre|meter|cm|mm|mil|mile|miles|inch|inç|inc|"
    r"feet|foot|ayak|yard|kg|kilogram|g|gram|lb|lbs|pound|libre|oz|ons|"
    r"litre|liter|l|ml|galon|gallon|fahrenheit|santigrat|celsius|kelvin|"
    r"saat|dakika|saniye|mph|kmh)\b",
    re.IGNORECASE,
)

_OPEN_TOKENS = frozenset(
    {
        "aç",
        "ac",
        "açar",
        "acar",
        "açsana",
        "acsana",
        "başlat",
        "baslat",
        "çalıştır",
        "calistir",
        "çalıştir",
        "open",
        "launch",
    }
)
_CLOSE_TOKENS = frozenset(
    {"kapat", "kapa", "sonlandır", "sonlandir", "kapatır", "kapatir", "close"}
)
_COPY_TOKENS = frozenset({"kopyala", "kopyalar", "kopyalasana", "copy"})
_SAVE_TOKENS = frozenset({"kaydet", "kaydetsene", "kaydetiver", "save"})
_DO_TOKENS = frozenset({"yap", "yapsana", "yapar", "yapabilir", "et", "etsene"})
_DEIXIS_TOKENS = frozenset(
    {
        "şunu",
        "sunu",
        "bunu",
        "bunları",
        "bunlari",
        "şunları",
        "sunlari",
        "onu",
        "seçiliyi",
        "seciliyi",
    }
)

@dataclass(frozen=True, slots=True)
class ComputerIntent:
    """Deterministik host/backend araç çağrıları."""

    calls: tuple[dict[str, Any], ...]
    categories: frozenset[str]

    summarize: bool
    reason: str

def _tokens(message: str) -> set[str]:
    return set(re.findall(r"[a-z0-9çğıöşü]+", message.casefold(), flags=re.UNICODE))

def _synthetic(tool_name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }

def match_known_app(message: str) -> str | None:
    """Mesajdaki bilinen uygulama takma adını döndürür."""
    text = message.casefold()
    for pattern, alias in _APP_ALIASES:
        if pattern.search(text):
            return alias
    return None

def match_special_folder(message: str) -> str | None:
    """Masaüstü / Belgeler / İndirilenler / Resimler takma adı."""
    text = message.casefold()
    for pattern, alias in _SPECIAL_FOLDERS:
        if pattern.search(text):
            return alias
    return None

def parse_volume_level(message: str) -> int | None:
    """Türkçe ses komutundan 0–100 seviye çıkarır."""
    text = message.casefold()
    if re.search(r"\b(sessiz|mute|sesi\s*kapat|sesi\s*kes)\b", text):
        return 0
    numbered = re.search(
        r"(?:ses(?:i|ini)?|volume)\s*(?:seviyesini\s*)?(?:yüzde\s*|%\s*)?(\d{1,3})\b",
        text,
    )
    if numbered is None:
        numbered = re.search(r"\b(?:yüzde|%)\s*(\d{1,3})\b", text)
    if numbered is not None:
        value = int(numbered.group(1))
        if 0 <= value <= 100:
            return value
    if re.search(r"\bsesi?\s*(kıs|kis|düşür|dusur)\b", text):
        return 20
    if re.search(r"\bsesi?\s*(yükselt|yukselt|aç|ac)\b", text):
        return 50
    return None

def is_screenshot_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"ekran\s*görüntüsü|ekran\s*goruntusu|screenshot|\bss\s*al\b|"
            r"ekran[ıi]\s*yakala|ekran[ıi]\s*çek|ekrani\s*cek",
            text,
        )
    )

def is_clipboard_read_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(pano(?:yu|da|daki)?|clipboard)\b", text)
        and re.search(r"\b(oku|okur|nedir|ne\s*var|göster|goster|yazıyor|yaziyor)\w*\b", text)
    )

def is_copy_selection_request(message: str) -> bool:
    tokens = _tokens(message)
    extra = {"seçili", "secili", "seçimi", "secimi"}
    if tokens & _COPY_TOKENS and tokens & (_DEIXIS_TOKENS | extra):
        return True
    text = message.casefold()
    if re.search(
        r"(?:şunu|sunu|bunu|onu|seçiliyi|seciliyi)\s+(?:panoya|clipboard)\s+(?:yaz|koy|ekle)",
        text,
    ):
        return True
    return bool(
        re.search(r"seçili\s*(metni?|yazıyı)?\s*kopyala|secili\s*(metni?)?\s*kopyala", text)
    )

def is_deixis_action(message: str) -> bool:
    """Şunu/bunu + yap/aç/kopyala — bağlam (seçim/pano/pencere) gerekir."""
    tokens = _tokens(message)
    if not (tokens & _DEIXIS_TOKENS):
        return False
    return bool(tokens & (_DO_TOKENS | _OPEN_TOKENS | _CLOSE_TOKENS | _COPY_TOKENS | _SAVE_TOKENS))

def is_lock_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"\b(bilgisayar[ıi]n?[ıi]?\s*kilitle|oturumu\s*kilitle|ekran[ıi]\s*kilitle|"
            r"lock\s*workstation|win\s*\+\s*l)\b",
            text,
        )
    )

def metric_tools(message: str) -> tuple[str, ...]:
    """Sistem ölçümü komutlarında okunacak araç adları."""
    text = message.casefold()
    if not re.search(
        r"\b(göster|goster|nedir|ne\s*kadar|kullanım|kullanim|durum|dolu)\w*\b",
        text,
    ):
        return ()
    names: list[str] = []
    if re.search(r"\b(gpu|ekran\s*kart|vram|nvidia)\b", text):
        names.append("get_gpu_usage")
    if re.search(r"\b(ram|bellek)\b", text) and not re.search(
        r"\b(hatırla|hatirla|kalıcı\s*hafıza)\b", text
    ):
        names.append("get_ram_usage")
    if re.search(r"\b(cpu|işlemci|islemci)\b", text):
        names.append("get_cpu_usage")
    if re.search(
        r"\b(disk\s*(doluluk|kullanım|kullanim|alan)|disk\b.*\b(dolu|yer|alan))\w*",
        text,
    ):
        names.append("get_disk_usage")
    return tuple(names)

def _leftover_topic_tokens(message: str) -> set[str]:
    tokens = _tokens(message)
    return {
        token
        for token in tokens
        if token not in _OPEN_TOKENS
        and token not in _CLOSE_TOKENS
        and token not in _APP_NOISE
        and len(token) > 2
    }

def is_bare_app_launch(message: str) -> bool:
    """Yalnızca uygulamayı aç/kapat — şarkı/video veya 'Chrome'da X' konusu yok."""
    if match_known_app(message) is None:
        return False
    tokens = _tokens(message)
    if not (tokens & (_OPEN_TOKENS | _CLOSE_TOKENS)):
        return False
    media_content = re.search(
        r"\b(şarkı|sarki|müzik|muzik|video|klip|film|parça|parca|albüm|album|"
        r"playlist|çalma\s*listesi|youtube|wikipedia)\w*\b",
        message.casefold(),
    )
    if media_content is not None:
        return False
    return not _leftover_topic_tokens(message)

def is_in_browser_lookup(message: str) -> bool:
    """'Chrome'da X ara/aç' — uygulamayı açmak değil, web araması."""
    if match_known_app(message) not in {"chrome", "edge", "firefox"}:
        return False
    if is_bare_app_launch(message):
        return False
    leftover = _leftover_topic_tokens(message)
    if not leftover:
        return False
    return bool(re.search(r"\b(ara|bul|göster|goster|aç|ac|git)\b", message.casefold()))

_MATH_EXPR = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:[+\-*/x×÷:]|\*\*)\s*\d",
    re.IGNORECASE,
)
_UNIT_Q = re.compile(
    r"\b(?:kaç\s+(?:mil|km|kilometre|metre|inch|inç|feet|ayak|kg|pound|lb|ons|"
    r"litre|galon|fahrenheit|santigrat|celsius|kelvin)|"
    r"birim\s*çevir|birim\s*cevir|çevir\s*birim|cevir\s*birim|"
    r"hesapla|topla\s+bunu|kaç\s+eder)\b",
    re.IGNORECASE,
)
_OPEN_CALC_APP = re.compile(r"hesap\s*makinesi|\bcalculator\b", re.IGNORECASE)

def is_currency_lookup(message: str) -> bool:
    """Döviz/kripto — calculate değil."""
    text = (message or "").casefold()
    if not _CURRENCY.search(text):
        return False
    return bool(re.search(r"\b(kaç|kac|fiyat|ne\s*kadar|kur|çevir|cevir)\b", text))

def is_crypto_lookup(message: str) -> bool:
    return bool(_CRYPTO.search(message or "") and is_currency_lookup(message))

def extract_fx_args(message: str) -> dict[str, Any] | None:
    """'100 dolar kaç TL' → Frankfurter fx_rate argümanı."""
    if not is_currency_lookup(message) or is_crypto_lookup(message):
        return None
    found: list[str] = []
    for pattern, code in _FIAT_ALIASES:
        if pattern.search(message) and code not in found:
            found.append(code)
    if not found:
        return None
    base = found[0]
    quote = found[1] if len(found) > 1 else ("TRY" if base != "TRY" else "USD")
    amount = 1.0
    numbered = re.search(r"(\d+(?:[.,]\d+)?)", message)
    if numbered:
        amount = float(numbered.group(1).replace(",", "."))
    return {"base": base, "quote": quote, "amount": amount}

def is_weather_request(message: str) -> bool:
    text = (message or "").casefold()
    return bool(
        re.search(
            r"\b(hava\s*durumu|hava\s*nasıl|hava\s*nasil|sıcaklık|sicaklik|"
            r"yağmur|yagmur|weather|forecast)\b",
            text,
        )
    )

def is_wiki_lookup_request(message: str) -> bool:
    if is_in_browser_lookup(message) or is_currency_lookup(message):
        return False
    text = (message or "").casefold()
    return bool(re.search(r"\b(wikipedia|viki(?:pedia)?|ansiklopedi|kimdir)\b", text))

def extract_wiki_title(message: str) -> str:
    text = re.sub(
        r"\b(wikipedia|viki(?:pedia)?|ansiklopedi|kimdir|nedir|hakkında|hakkinda|"
        r"maddesi|sayfası|sayfasi|ara|bak|göster|goster)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    title = " ".join(text.split()).strip(" ?!.")
    return title or message.strip()

def extract_weather_place(message: str) -> str:
    text = re.sub(
        r"\b(hava\s*durumu|hava\s*nasıl|hava\s*nasil|sıcaklık|sicaklik|"
        r"yağmur|yagmur|weather|forecast|nedir|nasıl|nasil|göster|goster|"
        r"bugün|bugun|yarın|yarin|lütfen|lutfen)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"['\u2019]?(da|de|ta|te)\b", " ", text, flags=re.IGNORECASE)
    place = " ".join(text.split()).strip(" ?!.")
    return place or "İstanbul"

def is_calculate_request(message: str) -> bool:
    """Aritmetik veya birim — Windows hesap makinesi uygulaması değil."""
    text = (message or "").strip()
    if not text or _OPEN_CALC_APP.search(text) or is_currency_lookup(text):
        return False
    return bool(_MATH_EXPR.search(text) or _UNIT_Q.search(text) or _UNIT_PAIR.search(text))

def extract_calculate_args(message: str) -> dict[str, Any] | None:
    """Türkçe hesap/birim cümlesinden calculate argümanı."""
    if not is_calculate_request(message):
        return None
    pair = _UNIT_PAIR.search(message)
    if pair:
        return {
            "value": float(pair.group(1).replace(",", ".")),
            "from_unit": pair.group(2),
            "to_unit": pair.group(3),
        }
    math = re.search(r"[\d(][\d\s.,+\-*/x×÷:()]+[\d)]", message)
    if math:
        return {"expression": math.group(0).strip()}
    rest = re.sub(r".*\bhesapla\b\s*", "", message, flags=re.IGNORECASE).strip()
    return {"expression": rest} if rest else None

def is_volume_query(message: str) -> bool:
    """Ses seviyesini oku — ayarlama değil."""
    text = message.casefold()
    if not re.search(r"\b(ses\w*|volume)\b", text):
        return False
    if re.search(
        r"\b(yap|ayarla|çek|cek|kıs|kis|yükselt|yukselt|mute|sessiz|kapat|kes)\b",
        text,
    ):
        return False
    return bool(re.search(r"\b(kaç|kac|nedir|ne\s*kadar|göster|goster|oku|seviye)\b", text))

def extract_clipboard_write(message: str) -> str | None:
    """'Panoya yaz X' — işaret zamiri değilse metni döndürür."""
    text = (message or "").strip()
    tokens = _tokens(text)
    if tokens & _DEIXIS_TOKENS:
        return None
    matched = re.search(
        r"(?:panoya|clipboard(?:['\u2019]?a)?)\s+(?:yaz|koy|ekle)\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if matched is None:
        matched = re.search(
            r"(?:yaz|koy)\s+(.+?)\s+(?:panoya|clipboard)\b",
            text,
            flags=re.IGNORECASE,
        )
    if matched is None:
        return None
    payload = matched.group(1).strip().strip("\"'")
    return payload or None

def is_clipboard_clear_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(pano(?:yu|yu)?|clipboard)\b", text)
        and re.search(r"\b(temizle|sil|boşalt|bosalt|clear)\b", text)
    )

def is_power_status_request(message: str) -> bool:
    text = message.casefold()
    if not re.search(r"\b(pil|şarj|sarj|batarya|güç\s*durum|guc\s*durum)\b", text):
        return False
    if re.search(r"\b(şarj\s*et|sarj\s*et|doldur)\b", text):
        return False
    return bool(re.search(r"\b(göster|goster|nedir|ne\s*kadar|durum|kaç|kac)\b", text))

def is_battery_level_request(message: str) -> bool:
    """Pil yüzdesi — prize takılı mı sorusu değil."""
    text = message.casefold()
    if re.search(r"\b(şarj\s*et|sarj\s*et|doldur)\b", text):
        return False
    return bool(
        re.search(r"\b(pil|şarj|sarj|batarya)\b", text)
        and re.search(r"\b(yüzde|yuzde|%|kaç\s*kal|kac\s*kal|seviye)\w*", text)
    )

def is_computer_info_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"bilgisayar\s*ad[ıi]|hostname|windows\s*sürüm|windows\s*surum|"
            r"kullanıcı\s*ad[ıi]m|kullanici\s*adim|os\s*(sürüm|surum|bilgi)|"
            r"makine\s*ad[ıi]",
            text,
        )
    )

def is_removable_drives_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(usb|çıkarılabilir|cikarilabilir|flash\s*bellek|takılı\s*disk|takili\s*disk)\b", text)
        and re.search(r"\b(göster|goster|nedir|listele|hangi|var\s*mı|var\s*mi)\w*", text)
    )

def is_printers_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(yazıcı|yazici|printer)\w*", text)
        and re.search(r"\b(listele|göster|goster|nedir|hangi|var\s*mı|var\s*mi)\w*", text)
    )

def extract_duplicate_file(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\b(çoğalt|cogalt|kopyasını\s*çıkar|kopyasini\s*cikar|duplicate)\w*", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_installed_app_query(message: str) -> str | None:
    text = message.casefold()
    if not re.search(r"\b(yüklü|yuklu|kurulu)\s*m[ıiuü]\b", text):
        return None
    app = match_known_app(message)
    return app

def extract_rename_file(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\b(adlandır|adlandir|rename|adını\s*değiştir|adini\s*degistir)\w*", text):
        return None
    names = re.findall(r"([\w.-]+\.\w{2,4})", message)
    if len(names) < 2:
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"source": f"{folder}/{names[0]}", "name": names[1]}

def extract_file_hash(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\b(hash|sha256|özet|ozet|checksum)\b", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_open_external_url(message: str) -> dict[str, Any] | None:
    if is_in_browser_lookup(message):
        return None
    matched = re.search(r"https?://[^\s<>\"']+", message)
    if matched is None:
        return None
    tokens = _tokens(message)
    text = message.casefold()
    if not (tokens & _OPEN_TOKENS or re.search(r"\b(link|adres|url)\b", text)):
        return None
    return {"url": matched.group(0).rstrip(".,);]}")}

def extract_process_running(message: str) -> dict[str, Any] | None:
    """chrome çalışıyor mu — liste/yüklü/aç değil."""
    if is_process_list_request(message) or extract_installed_app_query(message):
        return None
    text = message.casefold()
    if not re.search(
        r"\b(çalışıyor\s*m[ıiuü]|calisiyor\s*m[ıiuü]|açık\s*m[ıiuü]|acik\s*m[ıiuü]|running)\b",
        text,
    ):
        return None
    app = match_known_app(message)
    if app is None:
        return None
    return {"name": app}

def is_open_windows_request(message: str) -> bool:
    if is_foreground_query(message) or is_process_list_request(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"(açık|acik)\s*pencer|pencereleri?\s*listele|open\s*windows",
            text,
        )
    )

def is_default_browser_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"varsayılan\s*tarayıcı|varsayilan\s*tarayici|default\s*browser",
            text,
        )
    )

def is_locale_query(message: str) -> bool:
    text = message.casefold()
    if is_dict_lookup_request(message):
        return False
    return bool(
        re.search(
            r"sistem\s*dil|windows\s*dil|os\s*locale|yerel\s*ayar|locale\s*(nedir|ne)",
            text,
        )
    )

def extract_windows_settings(message: str) -> dict[str, Any] | None:
    """bluetooth ayarlarını aç — çıplak 'ayarları aç' değil."""
    if is_screenshot_request(message):
        return None
    if parse_volume_level(message) is not None:
        return None
    text = message.casefold()
    if not re.search(r"\b(ayar|settings)\w*", text):
        return None
    if not (_tokens(message) & _OPEN_TOKENS):
        return None
    if re.search(r"\bbluetooth\b", text):
        return {"page": "bluetooth"}
    if re.search(r"\b(wifi|wi-fi|wlan|kablosuz)\b", text):
        return {"page": "wifi"}
    if re.search(r"\b(ekran|görüntü|goruntu|display)\b", text) and not re.search(
        r"görüntü\s*sü|goruntu\s*su|screenshot",
        text,
    ):
        return {"page": "display"}
    if re.search(r"\b(ses|sound|audio)\b", text):
        return {"page": "sound"}
    if re.search(r"\b(güncelleme|guncelleme|update)\b", text):
        return {"page": "update"}
    if re.search(r"\b(hakkında|hakkinda|about)\b", text):
        return {"page": "about"}
    if re.search(r"\b(tarih|saat|datetime|clock)\b", text):
        return {"page": "datetime"}
    if re.search(r"\b(uygulama|apps?\s*features)\b", text):
        return {"page": "apps"}
    return None

def extract_eject_drive(message: str) -> dict[str, Any] | None:
    if is_removable_drives_request(message):
        return None
    text = message.casefold()
    if re.search(r"\b(boşalt|bosalt|format|biçim|bicim)\b", text):
        return None
    if not re.search(
        r"\b(çıkar|cikar|eject|güvenle\s*kaldır|guvenle\s*kaldir)\b",
        text,
    ):
        return None
    if not re.search(r"\b(usb|sürücü|surucu|disk|flash)\w*", text):
        return None
    matched = re.search(
        r"(?:^|[^\w])([A-Za-z])(?:\s*[:.]|\s+(?:sürücü|surucu|disk)|['\u2019]y[iı])",
        message,
    )
    if matched is None:
        return None
    return {"letter": matched.group(1).upper()}

def extract_file_exists(message: str) -> dict[str, Any] | None:
    if extract_installed_app_query(message) or extract_process_running(message):
        return None
    if is_removable_drives_request(message) or is_printers_request(message):
        return None
    text = message.casefold()
    if not re.search(r"\bvar\s*m[ıiuü]\b", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_copy_file_path(message: str) -> dict[str, Any] | None:
    if is_copy_selection_request(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(yolunu|tam\s*yol|path(?:ini)?)\s*kopyala\b", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_line_count(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if re.search(r"kaç\s*dosya|kac\s*dosya", text):
        return None
    if not re.search(r"\b(kaç\s*satır|kac\s*satir|satır\s*say|satir\s*say|line\s*count)\w*", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_trash_file(message: str) -> dict[str, Any] | None:
    """Dosyayı çöpe at — kutuyu boşaltmaz."""
    text = message.casefold()
    if re.search(r"\b(boşalt|bosalt|empty|kalıcı|kalici|wipe|format)\b", text):
        return None
    if not re.search(
        r"\b(çöpe\s*at|cope\s*at|geri\s*dönüşüme\s*at|geri\s*donusume\s*at|"
        r"recycle(?:'e)?\s*at|çöpe\s*gönder|cope\s*gonder)\b",
        text,
    ):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_git_status(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\bgit\s*(durumu|status)\b", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    body = re.sub(
        r"masaüst\w*|masaust\w*|desktop\w*|belgeler\w*|documents\w*|"
        r"indirilen\w*|downloads\w*|resimler\w*|pictures\w*",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\b(git|durumu|status|klasöründe|klasorunde|deposu|repo)\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    leftover = [token for token in body.split() if re.fullmatch(r"[\w.-]{2,}", token)]
    if leftover:
        return {"path": f"{folder}/{leftover[0]}"}
    return {"path": folder}

def is_system_time_query(message: str) -> bool:
    """saat kaç / bugünün tarihi — namaz/güneş/ayar değil."""
    if is_prayer_request(message) or is_sun_times_request(message) or is_holiday_request(message):
        return False
    if extract_windows_settings(message) is not None:
        return False
    if is_uptime_query(message) or is_idle_query(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"saat\s*kaç|saat\s*kac|saat\s*nedir|"
            r"bugünün\s*tarih|bugunun\s*tarih|tarih\s*nedir|bugün\s*günlerden|"
            r"bugun\s*gunlerden|what\s*time|local\s*time",
            text,
        )
        and not re.search(r"\b(namaz|ezan|uptime|açık\s*kalma|acik\s*kalma)\b", text)
    )

def is_dark_mode_query(message: str) -> bool:
    text = message.casefold()
    if extract_windows_settings(message) is not None:
        return False
    return bool(re.search(r"karanlık\s*mod|karanlik\s*mod|dark\s*mode|koyu\s*tema", text))

def is_internet_status_query(message: str) -> bool:
    if is_wifi_query(message) or is_network_query(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"internet\s*var\s*m|internet\s*çalış|internet\s*calis|online\s*m[ıiuü]|"
            r"bağlantı\s*var|baglanti\s*var|net\s*var\s*m",
            text,
        )
    )

def is_startup_apps_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"başlangıç\s*program|baslangic\s*program|startup\s*app|"
            r"açılışta\s*çalış|acilişta\s*calis|acilissta\s*calis|açılış\s*program",
            text,
        )
    )

def is_logical_drives_request(message: str) -> bool:
    if is_removable_drives_request(message) or extract_eject_drive(message):
        return False
    if metric_tools(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"(sürücüleri?|suruculeri?|diskleri?)\s*(listele|neler|göster|goster)|"
            r"hangi\s*(sürücü|surucu|disk)ler",
            text,
        )
    )

def is_recycle_bin_info(message: str) -> bool:
    if extract_trash_file(message) or is_recycle_bin_open(message):
        return False
    text = message.casefold()
    if re.search(r"\b(boşalt|bosalt|empty|wipe)\b", text):
        return False
    return bool(
        re.search(
            r"(çöp|cop|geri\s*dönüşüm|geri\s*donusum|recycle)\w*.*"
            r"(kaç|kac|kaç\s*öğe|kac\s*oge|dolu|boyut|ne\s*kadar)|"
            r"(kaç|kac)\s*(öğe|oge|dosya).*(çöp|cop|geri\s*dönüşüm|recycle)",
            text,
        )
    )

def extract_special_folder_path(message: str) -> dict[str, Any] | None:
    if extract_copy_file_path(message):
        return None
    text = message.casefold()
    if re.search(r"[\w.-]+\.\w{2,4}", message):
        return None
    if not re.search(r"\b(yolu|path)\b", text):
        return None
    if not re.search(r"\b(nedir|ne|göster|goster)\b", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"folder": folder}

def extract_folder_size(message: str) -> dict[str, Any] | None:
    if extract_file_info(message) or metric_tools(message):
        return None
    text = message.casefold()
    if re.search(r"[\w.-]+\.\w{2,4}", message):
        return None
    if not re.search(
        r"ne\s*kadar\s*yer|kaç\s*mb|kac\s*mb|kaç\s*gb|kac\s*gb|"
        r"kaplıyor|kapliyor|klasör\s*boyut|klasor\s*boyut|folder\s*size",
        text,
    ):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"path": folder}

def extract_app_path(message: str) -> dict[str, Any] | None:
    if extract_installed_app_query(message) or extract_process_running(message):
        return None
    if _tokens(message) & _OPEN_TOKENS:
        return None
    text = message.casefold()
    if not re.search(r"\b(nerede|yolu|path|kurulu)\b", text):
        return None
    if re.search(r"\b(yüklü|yuklu)\s*m[ıiuü]\b", text):
        return None
    app = match_known_app(message)
    if app is None:
        return None
    if not re.search(r"\b(nerede|kurulum\s*yol|exe\s*yol|yolu\s*nedir)\w*", text):
        return None
    return {"name": app}

_FILE_EXTS = (
    "pdf",
    "txt",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "zip",
    "mp3",
    "mp4",
    "md",
    "csv",
    "json",
)
_EXT_RE = re.compile(r"\b(" + "|".join(_FILE_EXTS) + r")\b", re.IGNORECASE)

def is_default_printer_request(message: str) -> bool:
    text = message.casefold()
    return bool(re.search(r"varsayılan\s*yazıcı|varsayilan\s*yazici|default\s*printer", text))

def extract_file_association(message: str) -> dict[str, Any] | None:
    if is_default_printer_request(message) or is_printers_request(message):
        return None
    text = message.casefold()
    if not re.search(
        r"hangi\s*program|ne\s*(ile|aç|ac)|ne\s*açar|ne\s*acar|assoc|ilişkilendir|iliskilendir",
        text,
    ):
        return None
    matched = _EXT_RE.search(message)
    if matched is None:
        return None
    return {"extension": matched.group(1).lower()}

def is_nearby_wifi_request(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"yakın\w*\s*(wifi|wi-fi|wlan|kablosuz|ağ|ag)|"
            r"çevre\w*\s*(wifi|wi-fi|wlan|kablosuz)|"
            r"(wifi|wi-fi|wlan)\w*\s*(tara|scan|listele|ağlar|aglar)",
            text,
        )
    )

def is_power_plan_request(message: str) -> bool:
    if is_power_status_request(message) or is_battery_level_request(message):
        return False
    text = message.casefold()
    return bool(re.search(r"güç\s*plan|guc\s*plan|power\s*plan", text))

def is_user_profile_request(message: str) -> bool:
    if extract_special_folder_path(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"kullanıcı\s*klasör|kullanici\s*klasor|profil\s*yol|ev\s*klasör|ev\s*klasor|"
            r"home\s*folder|user\s*profile",
            text,
        )
    )

def extract_files_by_extension(message: str) -> dict[str, Any] | None:
    if extract_file_association(message) or extract_file_search(message):
        return None
    if _LIST_HINT.search(message.casefold()) and re.search(r"kaç\s*dosya|kac\s*dosya", message.casefold()):
        return None
    text = message.casefold()
    if not re.search(r"\b(listele|göster|goster|dekiler|dosyalar)\w*", text):
        return None
    matched = _EXT_RE.search(message)
    folder = match_special_folder(message)
    if matched is None or folder is None:
        return None
    return {"path": folder, "extension": matched.group(1).lower()}

def extract_newest_file(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(
        r"en\s*son\s*(indirilen|dosya)|son\s*indirilen\s*dosya\b|en\s*yeni\s*dosya",
        text,
    ):
        return None
    folder = match_special_folder(message) or "downloads"
    return {"path": folder}

def extract_directory_empty(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if re.search(r"\b(pano|clipboard|geri\s*dönüşüm|geri\s*donusum|çöp|cop|recycle)\b", text):
        return None
    if not re.search(r"\bboş\s*m[ıiuü]|bos\s*m[ıiuü]|empty\b", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"path": folder}

def extract_largest_file(message: str) -> dict[str, Any] | None:
    """masaüstünde en büyük dosya — klasör boyutu / en yeni değil."""
    if extract_folder_size(message) or extract_newest_file(message):
        return None
    text = message.casefold()
    if not re.search(r"en\s*büyük\s*dosya|en\s*buyuk\s*dosya|largest\s*file", text):
        return None
    folder = match_special_folder(message) or "desktop"
    return {"path": folder}

def extract_count_by_extension(message: str) -> dict[str, Any] | None:
    """masaüstünde kaç pdf — kaç dosya / pdf listele değil."""
    if extract_file_association(message) or extract_file_search(message):
        return None
    text = message.casefold()
    if re.search(r"kaç\s*dosya|kac\s*dosya|kaç\s*öğe|kac\s*oge|kaç\s*satır|kac\s*satir", text):
        return None
    if not re.search(r"\b(kaç|kac|how\s*many)\b", text):
        return None
    matched = _EXT_RE.search(message)
    folder = match_special_folder(message)
    if matched is None or folder is None:
        return None
    return {"path": folder, "extension": matched.group(1).lower()}

def extract_subdirectories(message: str) -> dict[str, Any] | None:
    """masaüstündeki klasörler — içindekiler / mkdir / boş mu değil."""
    if extract_create_directory(message) or extract_directory_empty(message):
        return None
    text = message.casefold()
    if re.search(r"içindekiler|icindekiler|kaç\s*dosya|kac\s*dosya", text):
        return None
    if not re.search(
        r"klasörleri|klasorleri|alt\s*klasör|alt\s*klasor|"
        r"klasörler\s+(neler|listele|göster|goster)|"
        r"klasorler\s+(neler|listele|göster|goster)|subfolder|directories",
        text,
    ):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"path": folder}

def extract_today_files(message: str) -> dict[str, Any] | None:
    """bugün indirilenler — son indirilenler / en son dosya / haber değil."""
    if extract_newest_file(message) or extract_recent_files(message):
        return None
    if is_system_time_query(message):
        return None
    text = message.casefold()
    if re.search(r"ne\s*oldu|haber|gündem|gundem", text):
        return None
    if not re.search(r"\b(bugün|bugun|today)\b", text):
        return None
    if not re.search(r"indirilen|değişen|degisen|eklenen|dosya", text):
        return None
    folder = match_special_folder(message)
    if folder is None and re.search(r"indirilen", text):
        folder = "downloads"
    if folder is None:
        return None
    return {"path": folder, "limit": 20}

def is_last_boot_query(message: str) -> bool:
    """son açılış ne zaman — ne zamandır açık / başlangıç programı değil."""
    if is_uptime_query(message) or is_startup_apps_request(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"son\s*açılış|son\s*acilis|ne\s*zaman\s*açıldı|ne\s*zaman\s*acildi|"
            r"last\s*boot|son\s*boot",
            text,
        )
    )

def is_system_model_request(message: str) -> bool:
    """bilgisayar modeli — bilgisayar adı değil."""
    if is_computer_info_request(message):
        return False
    text = message.casefold()
    return bool(re.search(r"bilgisayar\s*model|cihaz\s*model|marka\s*model|system\s*model", text))

def is_night_light_query(message: str) -> bool:
    """gece ışığı — karanlık mod / ekran görüntüsü değil."""
    if is_dark_mode_query(message) or is_screenshot_request(message):
        return False
    text = message.casefold()
    return bool(re.search(r"gece\s*ışığ|gece\s*isig|night\s*light|mavi\s*ışık|mavi\s*isik", text))

def is_bluetooth_status_query(message: str) -> bool:
    """bluetooth açık mı — ayarları aç değil."""
    if extract_windows_settings(message) is not None:
        return False
    text = message.casefold()
    return bool(
        re.search(r"\bbluetooth\b", text)
        and re.search(r"açık\s*m|acik\s*m|durum|enabled|kapalı\s*m|kapali\s*m", text)
    )

def extract_oldest_file(message: str) -> dict[str, Any] | None:
    """masaüstünde en eski dosya — en yeni / en büyük değil."""
    if extract_newest_file(message) or extract_largest_file(message):
        return None
    text = message.casefold()
    if not re.search(r"en\s*eski\s*dosya|oldest\s*file", text):
        return None
    folder = match_special_folder(message) or "desktop"
    return {"path": folder}

def extract_count_subdirectories(message: str) -> dict[str, Any] | None:
    """masaüstünde kaç klasör — kaç dosya / klasörleri listele değil."""
    if extract_subdirectories(message) or extract_count_by_extension(message):
        return None
    if extract_create_directory(message) or extract_directory_empty(message):
        return None
    text = message.casefold()
    if re.search(r"kaç\s*dosya|kac\s*dosya|kaç\s*pdf|kac\s*pdf|kaç\s*satır|kac\s*satir", text):
        return None
    if not re.search(r"kaç\s*klasör|kac\s*klasor|how\s*many\s*folders?", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"path": folder}

def is_timezone_query(message: str) -> bool:
    """saat dilimi — saat kaç / tarih ayarı değil."""
    if is_system_time_query(message) or extract_windows_settings(message) is not None:
        return False
    text = message.casefold()
    return bool(re.search(r"saat\s*dilim|time\s*zone|timezone", text))

def is_temp_folder_request(message: str) -> bool:
    """geçici klasör — ev / masaüstü yolu değil."""
    if is_user_profile_request(message) or extract_special_folder_path(message):
        return False
    text = message.casefold()
    return bool(re.search(r"geçici\s*klasör|gecici\s*klasor|temp\s*(klasör|klasor|folder)", text))

def is_wallpaper_query(message: str) -> bool:
    """duvar kağıdı — ekran görüntüsü değil."""
    if is_screenshot_request(message):
        return False
    text = message.casefold()
    return bool(re.search(r"duvar\s*kağıd|duvar\s*kagid|wallpaper", text))

def is_wifi_radio_query(message: str) -> bool:
    """wifi açık mı — bağlı SSID / yakın ağ / internet değil."""
    if is_nearby_wifi_request(message) or is_internet_status_query(message):
        return False
    text = message.casefold()
    if re.search(r"hangi\s*a[gğ]|ssid|yakın|yakin|bağl[ıi]y|bagliy", text):
        return False
    return bool(
        re.search(r"\b(wifi|wi-fi|wlan|kablosuz)\b", text)
        and re.search(r"açık\s*m|acik\s*m|kapalı\s*m|kapali\s*m|radyo|radio", text)
    )

def is_playback_device_query(message: str) -> bool:
    """hangi hoparlör — ses kaç / ses ayarı değil."""
    if extract_windows_settings(message) is not None:
        return False
    if parse_volume_level(message) is not None:
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"hoparlör|hoparlor|ses\s*çıkış|ses\s*cikis|playback|"
            r"ses\s*aygıt|ses\s*aygit|varsayılan\s*hoparlör|varsayilan\s*hoparlor",
            text,
        )
    )

def extract_drive_label(message: str) -> dict[str, Any] | None:
    """C sürücüsünün adı — çıkar / doluluk / sürücü listesi değil."""
    if extract_eject_drive(message) or is_removable_drives_request(message):
        return None
    if is_logical_drives_request(message) or metric_tools(message):
        return None
    text = message.casefold()
    if not re.search(
        r"etiket|volume\s*label|sürücüsünün\s*ad|surucusunun\s*ad|"
        r"sürücünün\s*ad|surucunun\s*ad|sürücü\s*ad[ıi]|surucu\s*ad[ıi]",
        text,
    ):
        return None
    matched = re.search(
        r"(?:^|[^\w])([A-Za-z])(?:\s*[:.]|\s+(?:sürücü|surucu|disk)|['\u2019]n)",
        message,
    )
    letter = (matched.group(1) if matched else "C").upper()
    if letter not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        return None
    return {"letter": letter}

def extract_smallest_file(message: str) -> dict[str, Any] | None:
    """masaüstünde en küçük dosya — en büyük / eski / yeni değil."""
    if extract_largest_file(message) or extract_oldest_file(message) or extract_newest_file(message):
        return None
    text = message.casefold()
    if not re.search(r"en\s*küçük\s*dosya|en\s*kucuk\s*dosya|smallest\s*file", text):
        return None
    folder = match_special_folder(message) or "desktop"
    return {"path": folder}

def extract_this_week_files(message: str) -> dict[str, Any] | None:
    """bu hafta indirilenler — bugün / son indirilenler / haber değil."""
    if extract_today_files(message) or extract_newest_file(message) or extract_recent_files(message):
        return None
    if is_system_time_query(message):
        return None
    text = message.casefold()
    if re.search(r"\b(bugün|bugun|ne\s*oldu|haber|gündem|gundem)\b", text):
        return None
    if not re.search(r"bu\s*hafta|this\s*week", text):
        return None
    if not re.search(r"indirilen|değişen|degisen|eklenen|dosya", text):
        return None
    folder = match_special_folder(message)
    if folder is None and re.search(r"indirilen", text):
        folder = "downloads"
    if folder is None:
        return None
    return {"path": folder, "limit": 20}

def is_onedrive_path_request(message: str) -> bool:
    """onedrive klasörü — ev / geçici / masaüstü yolu değil."""
    if is_user_profile_request(message) or is_temp_folder_request(message):
        return False
    if extract_special_folder_path(message):
        return False
    text = message.casefold()
    return bool(re.search(r"onedrive|one\s*drive", text) and re.search(r"klasör|klasor|yol|folder|path", text))

def is_cpu_name_query(message: str) -> bool:
    """işlemci adı — CPU kullanımı değil."""
    text = message.casefold()
    if re.search(r"kullanım|kullanim|yüzde|yuzde|percent", text):
        return False
    return bool(re.search(r"(işlemci|islemci|cpu)\s*(ad[ıi]|ismi|model)", text))

def is_gpu_name_query(message: str) -> bool:
    """ekran kartı adı — GPU kullanımı değil."""
    text = message.casefold()
    if re.search(r"kullanım|kullanim|sıcak|sicak|vram|yüzde|yuzde", text):
        return False
    return bool(re.search(r"(ekran\s*kart[ıi]?|gpu)\s*(ad[ıi]|ismi|model)", text))

def is_gpu_usage_query(message: str) -> bool:
    """ekran kartı kullanımı — ad değil; metric_tools 'kartı' sınırını tamamlar."""
    if is_gpu_name_query(message):
        return False
    text = message.casefold()
    return bool(re.search(r"ekran\s*kart\w*\s*kullan|gpu\s*kullan", text))

def is_ethernet_status_query(message: str) -> bool:
    """ethernet bağlı mı — wifi / internet / IP değil."""
    if is_wifi_radio_query(message) or is_wifi_query(message) or is_nearby_wifi_request(message):
        return False
    if is_internet_status_query(message) or is_network_query(message):
        return False
    text = message.casefold()
    if re.search(r"\bip\b|adres", text):
        return False
    return bool(re.search(r"ethernet|kablolu\s*ağ|kablolu\s*ag|lan\s*bağ|lan\s*bag", text))

def is_recording_device_query(message: str) -> bool:
    """hangi mikrofon — hoparlör / ses kaç değil."""
    if is_playback_device_query(message) or extract_windows_settings(message) is not None:
        return False
    if parse_volume_level(message) is not None:
        return False
    text = message.casefold()
    return bool(re.search(r"mikrofon|microphone|kayıt\s*aygıt|kayit\s*aygit", text))

def is_refresh_rate_query(message: str) -> bool:
    """yenileme hızı — kaç monitör / çözünürlük değil."""
    if is_display_query(message) and not re.search(r"hertz|hz|yenileme", message.casefold()):
        return False
    text = message.casefold()
    return bool(re.search(r"yenileme\s*hız|yenileme\s*hiz|kaç\s*hertz|kac\s*hertz|refresh\s*rate|\bhz\b", text))

def extract_yesterday_files(message: str) -> dict[str, Any] | None:
    """dün indirilenler — bugün / bu hafta / son değil."""
    if extract_today_files(message) or extract_this_week_files(message):
        return None
    if extract_newest_file(message) or extract_recent_files(message):
        return None
    text = message.casefold()
    if re.search(r"\b(bugün|bugun|bu\s*hafta|ne\s*oldu|haber)\b", text):
        return None
    if not re.search(r"\b(dün|dun|yesterday)\b", text):
        return None
    if not re.search(r"indiril|download|değişen|degisen|eklenen|dosya", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        folder = "downloads"
    return {"path": folder, "limit": 20}

def extract_count_today_files(message: str) -> dict[str, Any] | None:
    """bugün kaç dosya indirildi — liste / kaç dosya (tümü) değil."""
    if extract_yesterday_files(message) or extract_this_week_files(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(bugün|bugun|today)\b", text):
        return None
    if not re.search(r"\b(kaç|kac|how\s*many)\b", text):
        return None
    if re.search(r"kaç\s*klasör|kac\s*klasor|kaç\s*satır|kac\s*satir", text):
        return None
    folder = match_special_folder(message)
    if folder is None and re.search(r"indiril|\bindi\b|download", text):
        folder = "downloads"
    if folder is None:
        return None
    return {"path": folder}

def is_screen_scale_query(message: str) -> bool:
    """ekran ölçeği — Hz / kaç monitör değil."""
    if is_refresh_rate_query(message):
        return False
    text = message.casefold()
    if re.search(r"kaç\s*monitör|kac\s*monitor|çözünürl|cozunurl", text):
        return False
    return bool(
        re.search(
            r"ölçe[kğg]|olcek|olcegi|scale\s*factor|\bdpi\b|ekran\s*scale|"
            r"ekran\s*yüzde\s*kaç|ekran\s*yuzde\s*kac",
            text,
        )
    )

def is_ram_size_query(message: str) -> bool:
    """kaç GB ram — RAM kullanımı değil."""
    text = message.casefold()
    if re.search(r"kullanım|kullanim|yüzde|yuzde|percent", text):
        return False
    return bool(
        re.search(r"\b(ram|bellek)\b", text)
        and re.search(r"kaç\s*gb|kac\s*gb|kaç\s*gb|ne\s*kadar|kapasite|toplam", text)
    )

def is_cpu_count_query(message: str) -> bool:
    """kaç çekirdek — işlemci adı / kullanım değil."""
    if is_cpu_name_query(message):
        return False
    text = message.casefold()
    if re.search(r"kullanım|kullanim|yüzde|yuzde|\bthread\b", text):
        return False
    return bool(
        re.search(
            r"kaç\s*(tane\s*)?çekirdek|kac\s*(tane\s*)?cekirdek|"
            r"çekirdek\s*(say|kaç)|cekirdek\s*(say|kac)|"
            r"kaç\s*(tane\s*)?core|core\s*count",
            text,
        )
    )

def is_mute_status_query(message: str) -> bool:
    """ses kapalı mı — sessiz yap / ses kaç değil."""
    if parse_volume_level(message) is not None and re.search(r"\b(yap|ol|et|ayarla)\b", message.casefold()):
        return False
    text = message.casefold()
    if re.search(r"\b(yap|ol|et|ayarla|kıs|kis|yükselt)\b", text):
        return False
    return bool(
        re.search(
            r"ses\s*kapalı\s*m|ses\s*kapali\s*m|ses\s*açık\s*m|ses\s*acik\s*m|"
            r"sessiz\s*m[ıiuü]|muted\s*m[ıiuü]",
            text,
        )
    )

def extract_drive_filesystem(message: str) -> dict[str, Any] | None:
    """C dosya sistemi — etiket / doluluk / çıkar değil."""
    if extract_drive_label(message) or extract_eject_drive(message):
        return None
    if is_logical_drives_request(message) or metric_tools(message):
        return None
    text = message.casefold()
    if re.search(r"formatla|biçimlendir|bicimlendir", text):
        return None
    if not re.search(r"dosya\s*sistem|file\s*system|\bntfs\b|\bfat32\b|format[ıi]", text):
        return None
    matched = re.search(
        r"(?:^|[^\w])([A-Za-z])(?:\s*[:.]|\s+(?:sürücü|surucu|disk)|['\u2019]n)",
        message,
    )
    letter = (matched.group(1) if matched else "C").upper()
    if letter not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        return None
    return {"letter": letter}

def is_airplane_mode_query(message: str) -> bool:
    """uçak modu — wifi açık mı / internet değil."""
    if is_wifi_radio_query(message) or is_internet_status_query(message):
        return False
    text = message.casefold()
    if re.search(r"uçakta\s+m[ıiuü]|ucakta\s+m[ıiuü]", text) and not re.search(
        r"uçak\s*mod|ucak\s*mod|airplane\s*mode", text
    ):
        return False
    return bool(re.search(r"uçak\s*mod|ucak\s*mod|airplane\s*mode", text))

def extract_this_month_files(message: str) -> dict[str, Any] | None:
    """bu ay indirilenler — bugün / hafta / dün değil."""
    if extract_today_files(message) or extract_this_week_files(message):
        return None
    if extract_yesterday_files(message) or extract_newest_file(message) or extract_recent_files(message):
        return None
    text = message.casefold()
    if re.search(r"\b(bugün|bugun|bu\s*hafta|dün|dun|ne\s*oldu|haber)\b", text):
        return None
    if not re.search(r"bu\s*ay|this\s*month", text):
        return None
    if not re.search(r"indiril|download|değişen|degisen|eklenen|dosya", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        folder = "downloads"
    return {"path": folder, "limit": 20}

def extract_count_yesterday_files(message: str) -> dict[str, Any] | None:
    """dün kaç dosya indirildi — liste / bugün sayı değil."""
    if extract_count_today_files(message) or extract_this_week_files(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(dün|dun|yesterday)\b", text):
        return None
    if not re.search(r"\b(kaç|kac|how\s*many)\b", text):
        return None
    if re.search(r"kaç\s*klasör|kac\s*klasor|kaç\s*satır|kac\s*satir", text):
        return None
    folder = match_special_folder(message)
    if folder is None and re.search(r"indiril|\bindi\b|download", text):
        folder = "downloads"
    if folder is None:
        return None
    return {"path": folder}

def is_os_version_query(message: str) -> bool:
    """windows sürümü — model / bilgisayar adı değil."""
    if is_system_model_request(message):
        return False
    text = message.casefold()
    if re.search(r"bilgisayar\s*ad[ıi]|hostname|makine\s*ad[ıi]", text):
        return False
    return bool(
        re.search(
            r"windows\s*sürüm|windows\s*surum|os\s*sürüm|os\s*surum|"
            r"hangi\s*windows|winver|işletim\s*sistemi\s*sür|isletim\s*sistemi\s*sur",
            text,
        )
    )

def is_username_query(message: str) -> bool:
    """kullanıcı adım — ev klasörü değil."""
    if is_user_profile_request(message):
        return False
    text = message.casefold()
    if re.search(r"klasör|klasor|yol|folder|path", text):
        return False
    return bool(
        re.search(
            r"kullanıcı\s*ad[ıi]m|kullanici\s*adim|username|"
            r"oturum\s*ad[ıi]|hangi\s*kullanıcı|hangi\s*kullanici",
            text,
        )
    )

def is_brightness_query(message: str) -> bool:
    """parlaklık — ölçek / gece ışığı / ses değil."""
    if is_night_light_query(message) or is_screen_scale_query(message):
        return False
    if is_volume_query(message) or parse_volume_level(message) is not None:
        return False
    text = message.casefold()
    return bool(re.search(r"parlaklık|parlaklik|brightness", text))

def is_vpn_status_query(message: str) -> bool:
    """vpn bağlı mı — wifi / ethernet / internet değil."""
    if is_wifi_radio_query(message) or is_wifi_query(message) or is_ethernet_status_query(message):
        return False
    if is_internet_status_query(message) or is_airplane_mode_query(message):
        return False
    text = message.casefold()
    return bool(re.search(r"\bvpn\b|sanal\s*özel|sanal\s*ozel", text))

def is_keyboard_layout_query(message: str) -> bool:
    """klavye dili — sistem locale değil."""
    if is_locale_query(message):
        return False
    text = message.casefold()
    return bool(re.search(r"klavye\s*dil|klavye\s*düzen|klavye\s*duzen|keyboard\s*layout", text))

def is_battery_saver_query(message: str) -> bool:
    """pil tasarrufu — pil yüzde / güç planı değil."""
    if is_battery_level_request(message) or is_power_plan_request(message):
        return False
    if is_power_status_request(message):
        return False
    text = message.casefold()
    return bool(re.search(r"pil\s*tasarruf|battery\s*saver|enerji\s*tasarruf", text))

def extract_count_this_week_files(message: str) -> dict[str, Any] | None:
    """bu hafta kaç dosya — liste / bugün-dün sayı değil."""
    if extract_count_today_files(message) or extract_count_yesterday_files(message):
        return None
    text = message.casefold()
    if not re.search(r"hafta(lık|ki|lik)?|this\s*week", text):
        return None
    if not re.search(r"\b(kaç|kac|how\s*many|sayı|sayi|count)\b", text):
        return None
    if re.search(r"kaç\s*klasör|kac\s*klasor|kaç\s*satır|kac\s*satir", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        folder = "downloads"
    return {"path": folder}

def extract_count_this_month_files(message: str) -> dict[str, Any] | None:
    """bu ay kaç dosya — liste / hafta sayı değil."""
    if extract_count_this_week_files(message) or extract_count_today_files(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(bu\s*ay|this\s*month|aylık|ayki|ay\s*kaç|ay\s*kac)\b", text):
        return None
    if not re.search(r"\b(kaç|kac|how\s*many|sayı|sayi|count)\b", text):
        return None
    if re.search(r"kaç\s*klasör|kac\s*klasor|kaç\s*satır|kac\s*satir", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        folder = "downloads"
    return {"path": folder}

def is_architecture_query(message: str) -> bool:
    """64 bit mi — Windows sürümü / işlemci adı değil."""
    if is_os_version_query(message) or is_cpu_name_query(message):
        return False
    text = message.casefold()
    return bool(
        re.search(r"64\s*bit|32\s*bit|\bx64\b|\bx86\b|mimari|architecture|kaç\s*bit|kac\s*bit|bitim", text)
    )

def is_focus_assist_query(message: str) -> bool:
    """odaklanma yardımı — sessiz / gece ışığı değil."""
    if is_mute_status_query(message) or is_night_light_query(message):
        return False
    if parse_volume_level(message) is not None:
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"odaklanma|odak\s*yard|rahatsız\s*etme|rahatsiz\s*etme|do\s*not\s*disturb|"
            r"focus\s*assist|bildirim(leri?)?\s*kapalı|bildirim(leri?)?\s*kapali",
            text,
        )
    )

def is_firewall_status_query(message: str) -> bool:
    """güvenlik duvarı — antivirüs değil."""
    text = message.casefold()
    if re.search(r"antivir|defender|windows\s*güvenlik\s*uygul", text):
        return False
    return bool(re.search(r"güvenlik\s*duvar|guvenlik\s*duvar|firewall", text))

def is_default_mail_query(message: str) -> bool:
    """hangi e-posta — tarayıcı değil."""
    if is_default_browser_request(message):
        return False
    text = message.casefold()
    return bool(
        re.search(
            r"e-?posta\s*uygul|hangi\s*(e-?posta|mail|posta)|varsayılan\s*(e-?posta|mail|posta)|"
            r"varsayilan\s*(e-?posta|mail|posta)|mailto|mail\s*client",
            text,
        )
    )

def is_screenshots_folder_query(message: str) -> bool:
    """ekran görüntüleri klasörü — ekran yakalama değil."""
    text = message.casefold()
    if re.search(r"\b(al|çek|cek|yakala)\b", text):
        return False
    if not re.search(r"klasör|klasor|yol|folder|path|nerede", text):
        return False
    return bool(re.search(r"ekran\s*görünt|ekran\s*gorunt|screenshot", text))

def is_wifi_signal_query(message: str) -> bool:
    """wifi sinyal — açık mı / SSID / yakın değil."""
    if is_wifi_radio_query(message) or is_nearby_wifi_request(message):
        return False
    text = message.casefold()
    return bool(
        re.search(r"\brssi\b|sinyal\s*güc|sinyal\s*guc", text)
        or (
            re.search(r"\b(wifi|wi-fi|wlan|kablosuz)\b", text)
            and re.search(r"sinyal|signal|çekim|cekim|rssi", text)
        )
    )

def is_idle_query(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(boşta|bosta|idle|kaç\s*dakika|kac\s*dakika)\w*", text)
        and re.search(r"\b(kal|süre|sure|dakika|saat|nedir|göster|goster)\w*", text)
    )

def is_network_query(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(r"\b(ip\s*adres|ağ\s*adres|ag\s*adres|local\s*ip|lan\s*ip)\w*", text)
        and re.search(r"\b(nedir|ne|göster|goster|kaç|kac)\w*", text)
    )

def is_display_query(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"\b(çözünürl|cozunurl|ekran\s*bilgi|kaç\s*ekran|kac\s*ekran|"
            r"kaç\s*monitör|kac\s*monitor|display)\w*",
            text,
        )
    )

def is_holiday_request(message: str) -> bool:
    text = (message or "").casefold()
    return bool(
        re.search(
            r"\b(resmi\s*tatil|kamu\s*tatil|bayram(?:lar)?|public\s*holiday)\w*",
            text,
        )
    )

def is_air_quality_request(message: str) -> bool:
    """Hava kirliliği / AQI — weather sıcaklık tahmini değil."""
    text = (message or "").casefold()
    return bool(
        re.search(
            r"\b(hava\s*kirlili|hava\s*kalite|partikül|partikul|aqi|pm2\.?5|pm10)\w*",
            text,
        )
    )

def extract_air_quality_place(message: str) -> str:
    text = re.sub(
        r"\b(hava\s*kirlili\w*|hava\s*kalite\w*|partikül\w*|partikul\w*|aqi|pm2\.?5|pm10|"
        r"nedir|nasıl|nasil|göster|goster|lütfen|lutfen)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"['\u2019]?(da|de|ta|te)\b", " ", text, flags=re.IGNORECASE)
    place = " ".join(text.split()).strip(" ?!.")
    return place or "İstanbul"

def is_read_selection_request(message: str) -> bool:
    """Şunu oku / ne seçili — panoyu değiştirmez."""
    text = message.casefold()
    tokens = _tokens(message)
    if tokens & _DEIXIS_TOKENS and re.search(r"\b(oku|okur|okuyuver)\b", text):
        return True
    return bool(
        re.search(
            r"\b(ne\s*seçili|ne\s*secili|seçili\s*(metin|yazı|yazi|ne)|"
            r"secili\s*(metin|yazi|ne))\b",
            text,
        )
    )

def _is_memory_or_shot_save(message: str) -> bool:
    text = message.casefold()
    if is_screenshot_request(message):
        return True
    return bool(
        re.search(
            r"\b(hafıza|hafiza|hatırla|hatirla|save_memory|belleğe|bellege)\b",
            text,
        )
    )

def is_save_clipboard_request(message: str) -> bool:
    if _is_memory_or_shot_save(message):
        return False
    text = message.casefold()
    return bool(
        re.search(r"\b(pano(?:yu|daki|dakini)?|clipboard)\b", text)
        and (bool(_tokens(message) & _SAVE_TOKENS) or re.search(r"\bnot\s*al\b", text))
    )

def is_save_selection_request(message: str) -> bool:
    """Şunu kaydet / seçiliyi not al — hafıza veya ekran görüntüsü değil."""
    if _is_memory_or_shot_save(message) or is_save_clipboard_request(message):
        return False
    tokens = _tokens(message)
    extra = {"seçili", "secili", "seçimi", "secimi"}
    if tokens & _SAVE_TOKENS and tokens & (_DEIXIS_TOKENS | extra):
        return True
    text = message.casefold()
    if re.search(r"\b(şunu|sunu|bunu|onu|seçiliyi|seciliyi)\s+not\s+(al|et)\b", text):
        return True
    if tokens & _DEIXIS_TOKENS and re.search(r"\b(ekle|append)\w*", text) and re.search(
        r"\.\w{2,4}", message
    ):
        return True
    if (
        tokens & _DEIXIS_TOKENS
        and match_special_folder(message)
        and re.search(r"\b(at|koy|koyuver|atıver|ativer)\b", text)
    ):
        return True
    return bool(
        re.search(
            r"seçili\s*(metni?|yazıyı)?\s*kaydet|secili\s*(metni?)?\s*kaydet|"
            r"seçiliyi\s*kaydet|seciliyi\s*kaydet",
            text,
        )
    )

def extract_save_selected(message: str) -> dict[str, Any]:
    args: dict[str, Any] = {"source": "selection", "mode": "create", "folder": "desktop"}
    if is_save_clipboard_request(message):
        args["source"] = "clipboard"
    text = message.casefold()
    if re.search(r"\b(ekle|append)\w*", text):
        args["mode"] = "append"
    folder = match_special_folder(message)
    if folder:
        args["folder"] = folder
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    if named:
        args["path"] = f"{folder}/{named.group(1)}" if folder else f"desktop/{named.group(1)}"
    return args

def is_postal_request(message: str) -> bool:
    if is_country_info_request(message) or is_in_browser_lookup(message):
        return False
    text = (message or "").casefold()
    return bool(
        re.search(r"\b(posta\s*kodu|postakodu|zip\s*code|zipcode)\w*", text)
        or re.search(r"\b\d{5}\b.*\b(neresi|hangi\s*il|posta)\b", text)
    )

def extract_postal_args(message: str) -> dict[str, Any]:
    numbered = re.search(r"\b(\d{5})\b", message)
    country = "TR"
    if re.search(r"\b(almanya|germany|deutschland|\bde\b)\b", message, flags=re.IGNORECASE):
        country = "DE"
    elif re.search(r"\b(amerika|usa|\bus\b)\b", message, flags=re.IGNORECASE):
        country = "US"
    return {"code": numbered.group(1) if numbered else "34000", "country": country}

def extract_create_note(message: str) -> dict[str, Any] | None:
    """Yeni not yaz — seçimi kaydetmez."""
    if is_save_selection_request(message) or is_save_clipboard_request(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(yeni\s+not|not\s+oluştur|not\s+olustur|not\s+yaz)\b", text):
        return None
    folder = match_special_folder(message) or "desktop"
    body = message
    for pattern, _alias in _SPECIAL_FOLDERS:
        body = pattern.sub(" ", body)
    body = re.sub(
        r"\b(yeni\s+not|not\s+oluştur|not\s+olustur|not\s+yaz|lütfen|lutfen|"
        r"olarak|adında|adinda)\b",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    content = " ".join(body.split()).strip(" :\"'")
    if not content:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return {"path": f"{folder}/uryx-not-{stamp}.txt", "content": content}

def is_foreground_query(message: str) -> bool:
    text = message.casefold()
    return bool(
        re.search(
            r"hangi\s*pencere|ön\s*planda|on\s*planda|aktif\s*pencere|"
            r"odaktaki\s*pencere|foreground",
            text,
        )
    )

def is_process_list_request(message: str) -> bool:
    text = message.casefold()
    if is_outlook_tasks_query(message):
        return False
    return bool(
        re.search(
            r"(çalışan|calisan)\s*(program|süreç|surec|process)|"
            r"süreçleri?\s*listele|surecleri?\s*listele|process\s*list|"
            r"görev(ler)?\s*list|gorev(ler)?\s*list",
            text,
        )
    )

def is_calendar_query(message: str) -> bool:
    """takvim / randevu / ajanda — uygulama açma ve görev listesi değil."""
    text = message.casefold()
    if re.search(r"görev(ler)?\s*list|gorev(ler)?\s*list", text):
        return False
    if re.search(r"\b(aç|açsana|ac|acsana|başlat|baslat|çalıştır|calistir)\w*", text) and re.search(
        r"uygulama|program|\bapp\b", text
    ):
        return False
    return bool(re.search(r"\btakvim|\brandevu|\bajanda|\bcalendar\b", text))

def is_outlook_tasks_query(message: str) -> bool:
    """outlook görevleri — Windows görev listesi / görev yöneticisi değil."""
    text = message.casefold()
    if re.search(r"görev\s*yöneticisi|gorev\s*yoneticisi|task\s*manager", text):
        return False
    if re.search(r"görev(ler)?\s*list|gorev(ler)?\s*list", text) and "outlook" not in text:
        return False
    return bool(re.search(r"\boutlook\b", text) and re.search(r"görev|gorev|\btasks?\b", text))

def is_installed_apps_request(message: str) -> bool:
    text = message.casefold()
    return bool(re.search(r"(kurulu|yüklü|yuklu)\s*(uygulama|program)", text))

def is_uptime_query(message: str) -> bool:
    text = message.casefold()
    if re.search(r"pencere|uygulama|program|wifi|wi-fi", text):
        return False
    return bool(
        re.search(
            r"ne\s*zamand[ıi]r\s*aç[ıi]k|kaç\s*saattir\s*aç|kac\s*saattir\s*ac|"
            r"\buptime\b|açık\s*kalma|acik\s*kalma",
            text,
        )
    )

def is_wifi_query(message: str) -> bool:
    text = message.casefold()
    if re.search(r"\b(ip\s*adres|local\s*ip|lan\s*ip)\w*", text):
        return False
    if re.search(r"hangi\s*a[gğ]a?\s*bağl|hangi\s*aga?\s*bagl", text):
        return True
    return bool(
        re.search(r"\b(wifi|wi-fi|wlan|kablosuz)\b", text)
        and re.search(r"\b(ad[ıi]|ismi|bağl|bagl|durum|nedir|hangi)\b", text)
    )

def extract_notify_body(message: str) -> str | None:
    matched = re.search(
        r"(?:bana\s+)?(?:bildir|bildirim\s+(?:göster|goster|gönder|gonder|at))\s+(.+)",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if matched is None:
        return None
    body = matched.group(1).strip().strip("\"'")
    return body or None

def extract_recent_files(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"son\s*(indirilen|indirdik|dosya)|indirilenlerde\s*son", text):
        return None
    folder = match_special_folder(message) or "downloads"
    return {"path": folder, "limit": 8}

def extract_show_in_folder(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(
        r"gezginde\s*(göster|goster)|klasörde\s*(göster|goster)|klasorde\s*(göster|goster)|"
        r"explorer.?da\s*(göster|goster)|show\s*in\s*folder",
        text,
    ):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    return {"path": folder}

def extract_create_directory(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\b(klasör|klasor)\w*", text):
        return None
    if not re.search(r"\b(oluştur|olustur|yarat|yeni)\w*", text):
        return None
    folder = match_special_folder(message)
    if folder is None:
        return None
    query = message
    for pattern, _alias in _SPECIAL_FOLDERS:
        query = pattern.sub(" ", query)
    query = re.sub(
        r"\b(ünde|unde|inde|ında|inda|nde|nda)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\b(yeni|klasör\w*|klasor\w*|oluştur\w*|olustur\w*|yarat\w*|adında|adinda|diye|"
        r"aç|ac|yap|lütfen|lutfen)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    name = " ".join(query.split()).strip("\"'")
    if not name or len(name) < 1 or re.search(r"[\\/]", name):
        return None
    return {"path": f"{folder}/{name}"}

def _mentioned_folders(message: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for pattern, alias in _SPECIAL_FOLDERS:
        match = pattern.search(message)
        if match:
            found.append((match.start(), alias))
    found.sort(key=lambda item: item[0])
    aliases: list[str] = []
    for _start, alias in found:
        if alias not in aliases:
            aliases.append(alias)
    return aliases

def extract_read_file(message: str) -> dict[str, Any] | None:
    """Özel klasördeki dosyayı oku — 'şunu oku' seçim değildir."""
    if is_read_selection_request(message) or is_clipboard_read_request(message):
        return None
    text = message.casefold()
    if not re.search(r"\b(oku|okur|okuyuver)\w*", text):
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folder = match_special_folder(message)
    if named is None or folder is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def extract_copy_or_move(message: str) -> tuple[str, dict[str, Any]] | None:
    text = message.casefold()
    if is_copy_selection_request(message):
        return None
    if re.search(r"\b(taşı|tasi|move)\w*", text):
        action = "move_file"
    elif re.search(r"\b(kopyala|kopyalar|copy)\w*", text):
        action = "copy_file"
    else:
        return None
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    folders = _mentioned_folders(message)
    if named is None or len(folders) < 2:
        return None
    name = named.group(1)
    return action, {
        "source": f"{folders[0]}/{name}",
        "destination": f"{folders[1]}/{name}",
    }

def is_dict_lookup_request(message: str) -> bool:
    if is_wiki_lookup_request(message) or is_in_browser_lookup(message):
        return False
    text = (message or "").casefold()
    return bool(
        re.search(
            r"\b(sözlük|sozluk|wiktionary|kelime\s*anlam\w*|tanım[ıi]?\s*nedir|"
            r"definition|ne\s+demek)\b",
            text,
        )
    )

def extract_dict_args(message: str) -> dict[str, Any]:
    lang = "tr"
    if re.search(r"\b(ingilizce|english)\b", message, flags=re.IGNORECASE):
        lang = "en"
    elif re.search(r"\b(almanca|deutsch|german)\b", message, flags=re.IGNORECASE):
        lang = "de"
    text = re.sub(
        r"\b(sözlük|sozluk|wiktionary|kelime\s*anlam\w*|tanım[ıi]?\s*nedir|"
        r"definition|ne\s+demek|nedir|ingilizce|english|almanca|deutsch|german)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    term = " ".join(text.split()).strip(" ?!.")
    return {"term": term or message.strip(), "lang": lang}

def is_earthquake_request(message: str) -> bool:
    if is_in_browser_lookup(message):
        return False
    text = (message or "").casefold()
    return bool(re.search(r"\b(deprem|earthquake|sismik|magnitude)\w*", text))

def extract_earthquake_args(message: str) -> dict[str, Any]:
    text = message.casefold()
    region = "world" if re.search(r"\b(dünya|dunya|world|global)\b", text) else "tr"
    return {"region": region, "days": 2}

def is_country_info_request(message: str) -> bool:
    if is_holiday_request(message) or is_wiki_lookup_request(message):
        return False
    text = (message or "").casefold()
    return bool(
        re.search(
            r"\b(başkent(?:i)?|baskent(?:i)?|nüfus(?:u)?|nufus(?:u)?|"
            r"ülke\s*kodu|ulke\s*kodu|iso\s*kod|country\s*code)\b",
            text,
        )
    )

def extract_country_query(message: str) -> str:
    text = re.sub(
        r"\b(başkent(?:i)?|baskent(?:i)?|nüfus(?:u)?|nufus(?:u)?|"
        r"ülke\s*kodu|ulke\s*kodu|iso\s*kod|country\s*code|neresi|nedir|"
        r"kaç|kac|göster|goster)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"['\u2019]?(nın|nin|nun|nün|in|ın)\b", " ", text, flags=re.IGNORECASE)
    query = " ".join(text.split()).strip(" ?!.")
    return query or "Türkiye"

def is_prayer_request(message: str) -> bool:
    if is_holiday_request(message):
        return False
    text = (message or "").casefold()
    return bool(re.search(r"\b(namaz|ezan|imsak|iftar|prayer\s*time|salah)\w*", text))

def extract_prayer_city(message: str) -> str:
    text = re.sub(
        r"\b(namaz\w*|ezan\w*|imsak\w*|iftar\w*|vakit\w*|prayer\s*time|salah|"
        r"nedir|göster|goster|lütfen|lutfen)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"['\u2019]?(da|de|ta|te)\b", " ", text, flags=re.IGNORECASE)
    city = " ".join(text.split()).strip(" ?!.")
    return city or "İstanbul"

def is_sun_times_request(message: str) -> bool:
    if is_prayer_request(message) or is_weather_request(message):
        return False
    text = (message or "").casefold()
    return bool(
        re.search(
            r"gün\s*(doğum|dogum|batım|batim)|sunrise|sunset|\buv\b|ultraviyole",
            text,
        )
    )

def extract_sun_place(message: str) -> str:
    text = re.sub(
        r"\b(gün\s*(doğum|dogum|batım|batim)\w*|sunrise|sunset|uv|ultraviyole|"
        r"güneş\w*|gunes\w*|nedir|ne\s*zaman|göster|goster)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"['\u2019]?(da|de|ta|te)\b", " ", text, flags=re.IGNORECASE)
    place = " ".join(text.split()).strip(" ?!.")
    return place or "İstanbul"

def extract_file_info(message: str) -> dict[str, Any] | None:
    text = message.casefold()
    if not re.search(r"\b(boyut|kaç\s*kb|kac\s*kb|dosya\s*bilgi|kaç\s*byte|kac\s*byte)\w*", text):
        return None
    folder = match_special_folder(message)
    named = re.search(r"([\w.-]+\.\w{2,4})", message)
    if folder is None or named is None:
        return None
    return {"path": f"{folder}/{named.group(1)}"}

def is_recycle_bin_open(message: str) -> bool:
    text = message.casefold()
    if not re.search(
        r"geri\s*dönüşüm|geri\s*donusum|çöp\s*kutu|cop\s*kutu|recycle\s*bin",
        text,
    ):
        return False
    return bool(_tokens(text) & _OPEN_TOKENS)

def extract_file_search(message: str) -> dict[str, Any] | None:
    """Özel klasörde veya izinli köklerde dosya adı/deseni ara."""
    if not _FILE_SEARCH_HINT.search(message):
        return None
    tokens = _tokens(message)
    if tokens & _OPEN_TOKENS or _LIST_HINT.search(message.casefold()):
        return None
    if is_in_browser_lookup(message) or is_wiki_lookup_request(message):
        return None
    folder = match_special_folder(message)
    if folder is None and not re.search(r"\b(dosya|pdf|xlsx|docx|\.\w{2,4})\b", message.casefold()):
        return None
    query = message
    for pattern, _alias in _SPECIAL_FOLDERS:
        query = pattern.sub(" ", query)
    query = re.sub(
        r"\b(ara|bul|nerede|nelerde|dosya|klasör|klasor|içinde|icinde|de|da)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = " ".join(query.split()).strip("\"'")
    if not query or len(query) < 2:
        return None
    args: dict[str, Any] = {"query": query}
    if folder:
        args["root"] = folder
    return args

def select_tool_categories(message: str) -> set[str] | None:
    """Net niyette araç kategorisini daralt; bilinmeyende tam katalog."""
    text = message.casefold()
    tokens = _tokens(message)
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "web",
            (
                "internet",
                "web",
                "araştır",
                "arastir",
                "güncel",
                "guncel",
                "haber",
                "foto",
                "görsel",
                "gorsel",
                "video",
                "youtube",
                "instagram",
                "gönderi",
                "gonderi",
                "paylaşım",
                "paylasim",
                "şarkı",
                "sarki",
                "müzik",
                "muzik",
                "site",
                "link",
                "hava",
                "fiyat",
                "dolar",
                "bitcoin",
                "euro",
                "sterlin",
                "kur",
            ),
        ),
        ("application", ("uygulama", "program", "pencere", "not defteri", "hesap makinesi")),
        (
            "filesystem",
            ("dosya", "klasör", "klasor", "dizin", "masaüstü", "masaustu", "indirilenler"),
        ),
        (
            "system",
            (
                "cpu",
                "gpu",
                "ram",
                "bellek",
                "disk",
                "sistem",
                "işlemci",
                "islemci",
                "ekran görüntüsü",
                "ekran goruntusu",
                "screenshot",
                "ses seviyesi",
                "sesi aç",
                "sesi kapat",
                "pano",
                "clipboard",
                "sesi kıs",
                "sesi kis",
            ),
        ),
        ("docker", ("docker", "container", "konteyner")),
        ("git", ("git", "commit", "branch", "dal", "repository", "repo")),
        ("shell", ("terminal", "powershell", "komut satırı", "komut satiri")),
        ("rag", ("belgelerimde", "doküman", "dokuman", "pdf", "belge tabanı", "belge tabani")),
        ("memory", ("hatırla", "hatirla", "unut", "hafıza", "hafiza")),
    )
    matched = {category for category, words in groups if any(word in text for word in words)}
    if match_known_app(message):
        matched.add("application")
    if match_special_folder(message):
        matched.add("filesystem")
    if is_screenshot_request(message) or parse_volume_level(message) is not None:
        matched.add("system")
    if is_calculate_request(message):
        matched.add("system")
    if is_currency_lookup(message):
        matched.add("web")
        matched.discard("system")
    if is_volume_query(message) or is_power_status_request(message):
        matched.add("system")
    if (
        is_battery_level_request(message)
        or is_computer_info_request(message)
        or is_removable_drives_request(message)
    ):
        matched.add("system")
    if extract_rename_file(message) or extract_file_hash(message):
        matched.add("filesystem")
    if extract_open_external_url(message):
        matched.add("web")
        matched.discard("application")
    if is_in_browser_lookup(message):
        matched.add("web")
        matched.discard("application")
    if is_weather_request(message) or is_wiki_lookup_request(message) or is_holiday_request(message):
        matched.add("web")
    if is_air_quality_request(message):
        matched.add("web")
        matched.discard("system")
    if (
        is_dict_lookup_request(message)
        or is_earthquake_request(message)
        or is_country_info_request(message)
        or is_prayer_request(message)
        or is_sun_times_request(message)
        or is_postal_request(message)
    ):
        matched.add("web")
    if extract_read_file(message) or extract_copy_or_move(message):
        matched.add("filesystem")
    if is_recycle_bin_open(message):
        matched.add("filesystem")
    if (
        is_uptime_query(message)
        or is_wifi_query(message)
        or is_foreground_query(message)
        or is_process_list_request(message)
        or is_read_selection_request(message)
        or is_save_selection_request(message)
        or is_save_clipboard_request(message)
    ):
        matched.add("system")
    if is_save_selection_request(message) or is_save_clipboard_request(message) or extract_create_note(
        message
    ):
        matched.add("filesystem")
    if is_installed_apps_request(message) or extract_installed_app_query(message):
        matched.add("application")
    if is_printers_request(message):
        matched.add("system")
    if extract_duplicate_file(message):
        matched.add("filesystem")
    if (
        extract_file_exists(message)
        or extract_copy_file_path(message)
        or extract_line_count(message)
        or extract_trash_file(message)
    ):
        matched.add("filesystem")
    if extract_git_status(message):
        matched.add("git")
        matched.discard("shell")
    if extract_process_running(message) or is_open_windows_request(message):
        matched.add("system")
    if is_default_browser_request(message) or is_locale_query(message):
        matched.add("system")
    if (
        is_system_time_query(message)
        or is_dark_mode_query(message)
        or is_internet_status_query(message)
        or is_startup_apps_request(message)
        or is_logical_drives_request(message)
    ):
        matched.add("system")
    if is_recycle_bin_info(message) or extract_special_folder_path(message) or extract_folder_size(
        message
    ):
        matched.add("filesystem")
    if extract_app_path(message):
        matched.add("application")
    if (
        is_default_printer_request(message)
        or extract_file_association(message)
        or is_nearby_wifi_request(message)
        or is_power_plan_request(message)
        or is_user_profile_request(message)
    ):
        matched.add("system")
    if (
        extract_files_by_extension(message)
        or extract_newest_file(message)
        or extract_directory_empty(message)
        or extract_largest_file(message)
        or extract_count_by_extension(message)
        or extract_subdirectories(message)
        or extract_today_files(message)
        or extract_oldest_file(message)
        or extract_count_subdirectories(message)
        or extract_smallest_file(message)
        or extract_this_week_files(message)
        or extract_yesterday_files(message)
        or extract_count_today_files(message)
        or extract_this_month_files(message)
        or extract_count_yesterday_files(message)
        or extract_count_this_week_files(message)
        or extract_count_this_month_files(message)
        or is_screenshots_folder_query(message)
    ):
        matched.add("filesystem")
    if (
        is_last_boot_query(message)
        or is_system_model_request(message)
        or is_night_light_query(message)
        or is_bluetooth_status_query(message)
        or is_timezone_query(message)
        or is_temp_folder_request(message)
        or is_wallpaper_query(message)
        or is_wifi_radio_query(message)
        or is_playback_device_query(message)
        or extract_drive_label(message)
        or is_onedrive_path_request(message)
        or is_cpu_name_query(message)
        or is_gpu_name_query(message)
        or is_gpu_usage_query(message)
        or is_ethernet_status_query(message)
        or is_recording_device_query(message)
        or is_refresh_rate_query(message)
        or is_screen_scale_query(message)
        or is_ram_size_query(message)
        or is_cpu_count_query(message)
        or is_mute_status_query(message)
        or extract_drive_filesystem(message)
        or is_airplane_mode_query(message)
        or is_os_version_query(message)
        or is_username_query(message)
        or is_brightness_query(message)
        or is_vpn_status_query(message)
        or is_keyboard_layout_query(message)
        or is_battery_saver_query(message)
        or is_architecture_query(message)
        or is_focus_assist_query(message)
        or is_firewall_status_query(message)
        or is_default_mail_query(message)
        or is_wifi_signal_query(message)
    ):
        matched.add("system")
    if extract_windows_settings(message):
        matched.add("application")
    if extract_eject_drive(message):
        matched.add("system")
    if extract_recent_files(message) or extract_show_in_folder(message) or extract_create_directory(
        message
    ) or extract_file_info(message):
        matched.add("filesystem")
    if extract_notify_body(message):
        matched.add("system")
    if is_deixis_action(message):
        matched.update({"application", "system", "filesystem"})
    if "spotify" in text and not (
        re.search(r"\b(şarkı|sarki|müzik|muzik|video|çalma\s*listesi)\w*\b", text)
    ):
        matched.discard("web")
        matched.add("application")

    if not matched:
        return None

    if tokens & (_OPEN_TOKENS | _CLOSE_TOKENS):
        matched.add("application")
    return matched

def resolve_computer_intent(message: str) -> ComputerIntent | None:
    """Günlük Windows işleri için araç çağrısı üret; emin değilse None."""
    text = (message or "").strip()
    if not text:
        return None
    tokens = _tokens(text)

    if is_copy_selection_request(text):
        return ComputerIntent(
            calls=(_synthetic("copy_selected_text", {}, "intent_copy_selected"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="copy_selected",
        )

    if is_read_selection_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_selected_text", {}, "intent_read_selected"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_selected_text",
        )

    if is_save_selection_request(text) or is_save_clipboard_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "save_selected_text",
                    extract_save_selected(text),
                    "intent_save_selected",
                ),
            ),
            categories=frozenset({"system", "filesystem"}),
            summarize=True,
            reason="save_selected_text",
        )

    created_note = extract_create_note(text)
    if created_note is not None:
        return ComputerIntent(
            calls=(_synthetic("create_file", created_note, "intent_create_note"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="create_file",
        )

    if is_clipboard_read_request(text):
        return ComputerIntent(
            calls=(_synthetic("clipboard_read", {}, "intent_clipboard_read"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="clipboard_read",
        )

    if is_clipboard_clear_request(text):
        return ComputerIntent(
            calls=(_synthetic("clipboard_clear", {}, "intent_clipboard_clear"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="clipboard_clear",
        )

    clip_write = extract_clipboard_write(text)
    if clip_write is not None:
        return ComputerIntent(
            calls=(_synthetic("clipboard_write", {"text": clip_write}, "intent_clipboard_write"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="clipboard_write",
        )

    if is_recording_device_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_default_recording_device", {}, "intent_mic"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_default_recording_device",
        )

    if is_playback_device_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_default_playback_device", {}, "intent_playback"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_default_playback_device",
        )

    if is_mute_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_mute_status", {}, "intent_mute"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_mute_status",
        )

    if is_volume_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_volume", {}, "intent_get_volume"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_volume",
        )

    volume = parse_volume_level(text)
    if volume is not None and re.search(r"\b(ses\w*|volume|sessiz|mute)\b", text.casefold()):
        return ComputerIntent(
            calls=(_synthetic("set_volume", {"level": volume}, "intent_set_volume"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="set_volume",
        )

    if is_battery_saver_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_battery_saver", {}, "intent_saver"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_battery_saver",
        )

    if is_battery_level_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_battery_level", {}, "intent_battery"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_battery_level",
        )

    if is_power_status_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_power_status", {}, "intent_power"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_power_status",
        )

    if is_power_plan_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_power_plan", {}, "intent_power_plan"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_power_plan",
        )

    if is_system_model_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_system_model", {}, "intent_model"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_system_model",
        )

    if is_architecture_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_architecture", {}, "intent_arch"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_architecture",
        )

    if is_os_version_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_os_version", {}, "intent_os"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_os_version",
        )

    if is_username_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_username", {}, "intent_user"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_username",
        )

    if is_computer_info_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_computer_info", {}, "intent_computer"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_computer_info",
        )

    if is_keyboard_layout_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_keyboard_layout", {}, "intent_kbd"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_keyboard_layout",
        )

    if is_locale_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_system_locale", {}, "intent_locale"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_system_locale",
        )

    if is_brightness_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_brightness", {}, "intent_bright"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_brightness",
        )

    if is_night_light_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_night_light", {}, "intent_night"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_night_light",
        )

    if is_dark_mode_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_dark_mode", {}, "intent_dark"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_dark_mode",
        )

    if is_bluetooth_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_bluetooth_status", {}, "intent_bt"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_bluetooth_status",
        )

    if is_timezone_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_timezone", {}, "intent_tz"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_timezone",
        )

    if is_system_time_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_system_time", {}, "intent_time"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_system_time",
        )

    if is_default_mail_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_default_mail_app", {}, "intent_mail"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_default_mail_app",
        )

    if is_default_browser_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_default_browser", {}, "intent_browser"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_default_browser",
        )

    filesystem = extract_drive_filesystem(text)
    if filesystem is not None:
        return ComputerIntent(
            calls=(_synthetic("get_drive_filesystem", filesystem, "intent_fs"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_drive_filesystem",
        )

    labeled = extract_drive_label(text)
    if labeled is not None:
        return ComputerIntent(
            calls=(_synthetic("get_drive_label", labeled, "intent_label"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_drive_label",
        )

    ejected = extract_eject_drive(text)
    if ejected is not None:
        return ComputerIntent(
            calls=(_synthetic("eject_removable_drive", ejected, "intent_eject"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="eject_removable_drive",
        )

    if is_removable_drives_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_removable_drives", {}, "intent_usb"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_removable_drives",
        )

    if is_logical_drives_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_logical_drives", {}, "intent_drives"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_logical_drives",
        )

    opened_link = extract_open_external_url(text)
    if opened_link is not None:
        return ComputerIntent(
            calls=(_synthetic("open_external_url", opened_link, "intent_open_url"),),
            categories=frozenset({"web"}),
            summarize=True,
            reason="open_external_url",
        )

    if is_crypto_lookup(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "web_search",
                    {"query": text, "max_results": 5},
                    "intent_crypto_web",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=False,
            reason="crypto_web",
        )

    fx_args = extract_fx_args(text)
    if fx_args is not None:
        return ComputerIntent(
            calls=(_synthetic("fx_rate", fx_args, "intent_fx"),),
            categories=frozenset({"web"}),
            summarize=True,
            reason="fx_rate",
        )

    if is_air_quality_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "air_quality",
                    {"place": extract_air_quality_place(text)},
                    "intent_air_quality",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="air_quality",
        )

    if is_prayer_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "prayer_times",
                    {"city": extract_prayer_city(text), "country": "TR"},
                    "intent_prayer",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="prayer_times",
        )

    if is_sun_times_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "sun_times",
                    {"place": extract_sun_place(text)},
                    "intent_sun",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="sun_times",
        )

    if is_weather_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "weather",
                    {"place": extract_weather_place(text)},
                    "intent_weather",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="weather",
        )

    if is_holiday_request(text):
        return ComputerIntent(
            calls=(_synthetic("public_holidays", {"country": "TR"}, "intent_holidays"),),
            categories=frozenset({"web"}),
            summarize=True,
            reason="public_holidays",
        )

    if is_country_info_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "country_info",
                    {"query": extract_country_query(text)},
                    "intent_country",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="country_info",
        )

    if is_postal_request(text):
        return ComputerIntent(
            calls=(_synthetic("postal_lookup", extract_postal_args(text), "intent_postal"),),
            categories=frozenset({"web"}),
            summarize=True,
            reason="postal_lookup",
        )

    if is_in_browser_lookup(text):
        topic = " ".join(sorted(_leftover_topic_tokens(text)))
        return ComputerIntent(
            calls=(
                _synthetic(
                    "web_search",
                    {"query": topic or text, "max_results": 5},
                    "intent_browser_web",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=False,
            reason="in_browser_web",
        )

    if is_wiki_lookup_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "wiki_lookup",
                    {"title": extract_wiki_title(text), "lang": "tr"},
                    "intent_wiki",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="wiki_lookup",
        )

    if is_dict_lookup_request(text):
        return ComputerIntent(
            calls=(_synthetic("dict_lookup", extract_dict_args(text), "intent_dict"),),
            categories=frozenset({"web"}),
            summarize=True,
            reason="dict_lookup",
        )

    if is_earthquake_request(text):
        return ComputerIntent(
            calls=(
                _synthetic(
                    "earthquakes",
                    extract_earthquake_args(text),
                    "intent_quakes",
                ),
            ),
            categories=frozenset({"web"}),
            summarize=True,
            reason="earthquakes",
        )

    calc_args = extract_calculate_args(text)
    if calc_args is not None:
        return ComputerIntent(
            calls=(_synthetic("calculate", calc_args, "intent_calculate"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="calculate",
        )

    if is_wifi_signal_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_wifi_signal", {}, "intent_signal"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_wifi_signal",
        )

    if is_firewall_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_firewall_status", {}, "intent_fw"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_firewall_status",
        )

    if is_focus_assist_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_focus_assist", {}, "intent_focus"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_focus_assist",
        )

    if is_vpn_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_vpn_status", {}, "intent_vpn"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_vpn_status",
        )

    if is_airplane_mode_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_airplane_mode", {}, "intent_airplane"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_airplane_mode",
        )

    if is_ethernet_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_ethernet_status", {}, "intent_eth"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_ethernet_status",
        )

    if is_wifi_radio_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_wifi_radio", {}, "intent_wifi_radio"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_wifi_radio",
        )

    if is_last_boot_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_last_boot_time", {}, "intent_boot"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_last_boot_time",
        )

    if is_uptime_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_uptime", {}, "intent_uptime"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_uptime",
        )

    if is_nearby_wifi_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_nearby_wifi", {}, "intent_nearby_wifi"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_nearby_wifi",
        )

    if is_wifi_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_wifi_status", {}, "intent_wifi"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_wifi_status",
        )

    if is_internet_status_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_internet_status", {}, "intent_net_status"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_internet_status",
        )

    if is_foreground_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_foreground_window", {}, "intent_foreground"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_foreground_window",
        )

    if is_open_windows_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_open_windows", {}, "intent_windows"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_open_windows",
        )

    running = extract_process_running(text)
    if running is not None:
        return ComputerIntent(
            calls=(_synthetic("is_process_running", running, "intent_running"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="is_process_running",
        )

    if is_calendar_query(text):
        return ComputerIntent(
            calls=(_synthetic("list_calendar_events", {}, "intent_calendar"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_calendar_events",
        )

    if is_outlook_tasks_query(text):
        return ComputerIntent(
            calls=(_synthetic("list_outlook_tasks", {}, "intent_outlook_tasks"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_outlook_tasks",
        )

    if is_process_list_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_processes", {}, "intent_processes"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_processes",
        )

    installed_query = extract_installed_app_query(text)
    if installed_query is not None:
        return ComputerIntent(
            calls=(
                _synthetic(
                    "list_installed_applications",
                    {"query": installed_query},
                    "intent_app_installed",
                ),
            ),
            categories=frozenset({"application"}),
            summarize=True,
            reason="list_installed_applications",
        )

    app_path = extract_app_path(text)
    if app_path is not None:
        return ComputerIntent(
            calls=(_synthetic("resolve_application_path", app_path, "intent_app_path"),),
            categories=frozenset({"application"}),
            summarize=True,
            reason="resolve_application_path",
        )

    if is_default_printer_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_default_printer", {}, "intent_default_printer"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_default_printer",
        )

    associated = extract_file_association(text)
    if associated is not None:
        return ComputerIntent(
            calls=(_synthetic("get_file_association", associated, "intent_assoc"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_file_association",
        )

    if is_printers_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_printers", {}, "intent_printers"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_printers",
        )

    if is_installed_apps_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_installed_applications", {}, "intent_installed"),),
            categories=frozenset({"application"}),
            summarize=True,
            reason="list_installed_applications",
        )

    if is_startup_apps_request(text):
        return ComputerIntent(
            calls=(_synthetic("list_startup_apps", {}, "intent_startup"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="list_startup_apps",
        )

    notify_body = extract_notify_body(text)
    if notify_body is not None:
        return ComputerIntent(
            calls=(
                _synthetic(
                    "notify_user",
                    {"title": "Uryx", "body": notify_body},
                    "intent_notify",
                ),
            ),
            categories=frozenset({"system"}),
            summarize=True,
            reason="notify_user",
        )

    if is_idle_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_idle_time", {}, "intent_idle"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_idle_time",
        )

    if is_screen_scale_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_screen_scale", {}, "intent_scale"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_screen_scale",
        )

    if is_refresh_rate_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_refresh_rate", {}, "intent_hz"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_refresh_rate",
        )

    if is_display_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_display_info", {}, "intent_display"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_display_info",
        )

    if is_network_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_network_interfaces", {}, "intent_net"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_network_interfaces",
        )

    if is_wallpaper_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_wallpaper_path", {}, "intent_wallpaper"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_wallpaper_path",
        )

    if is_screenshots_folder_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_screenshots_folder", {}, "intent_ss_folder"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_screenshots_folder",
        )

    if is_screenshot_request(text):
        return ComputerIntent(
            calls=(_synthetic("take_screenshot", {}, "intent_screenshot"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="screenshot",
        )

    if is_lock_request(text):
        return ComputerIntent(
            calls=(_synthetic("lock_workstation", {}, "intent_lock"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="lock",
        )

    if is_cpu_count_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_cpu_count", {}, "intent_cores"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_cpu_count",
        )

    if is_ram_size_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_ram_size", {}, "intent_ram_size"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_ram_size",
        )

    if is_cpu_name_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_cpu_name", {}, "intent_cpu_name"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_cpu_name",
        )

    if is_gpu_name_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_gpu_name", {}, "intent_gpu_name"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_gpu_name",
        )

    if is_gpu_usage_query(text):
        return ComputerIntent(
            calls=(_synthetic("get_gpu_usage", {}, "intent_gpu_usage"),),
            categories=frozenset({"system"}),
            summarize=False,
            reason="get_gpu_usage",
        )

    metrics = metric_tools(text)
    if metrics:
        return ComputerIntent(
            calls=tuple(
                _synthetic(name, {}, f"intent_{name}") for name in metrics
            ),
            categories=frozenset({"system"}),
            summarize=False,
            reason="metrics",
        )

    trashed = extract_trash_file(text)
    if trashed is not None:
        return ComputerIntent(
            calls=(_synthetic("delete_file", trashed, "intent_trash"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="delete_file",
        )

    if is_recycle_bin_info(text):
        return ComputerIntent(
            calls=(_synthetic("get_recycle_bin_info", {}, "intent_recycle_info"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_recycle_bin_info",
        )

    if is_recycle_bin_open(text):
        return ComputerIntent(
            calls=(_synthetic("open_recycle_bin", {}, "intent_recycle"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="open_recycle_bin",
        )

    created = extract_create_directory(text)
    if created is not None:
        return ComputerIntent(
            calls=(_synthetic("create_directory", created, "intent_mkdir"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="create_directory",
        )

    shown = extract_show_in_folder(text)
    if shown is not None:
        return ComputerIntent(
            calls=(_synthetic("show_in_folder", shown, "intent_show_folder"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="show_in_folder",
        )

    counted_week = extract_count_this_week_files(text)
    if counted_week is not None:
        return ComputerIntent(
            calls=(_synthetic("count_this_week_files", counted_week, "intent_count_week"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_this_week_files",
        )

    counted_month = extract_count_this_month_files(text)
    if counted_month is not None:
        return ComputerIntent(
            calls=(_synthetic("count_this_month_files", counted_month, "intent_count_month"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_this_month_files",
        )

    counted_yesterday = extract_count_yesterday_files(text)
    if counted_yesterday is not None:
        return ComputerIntent(
            calls=(_synthetic("count_yesterday_files", counted_yesterday, "intent_count_yday"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_yesterday_files",
        )

    month_files = extract_this_month_files(text)
    if month_files is not None:
        return ComputerIntent(
            calls=(_synthetic("list_this_month_files", month_files, "intent_month"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_this_month_files",
        )

    yesterday = extract_yesterday_files(text)
    if yesterday is not None:
        return ComputerIntent(
            calls=(_synthetic("list_yesterday_files", yesterday, "intent_yesterday"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_yesterday_files",
        )

    counted_today = extract_count_today_files(text)
    if counted_today is not None:
        return ComputerIntent(
            calls=(_synthetic("count_today_files", counted_today, "intent_count_today"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_today_files",
        )

    week_files = extract_this_week_files(text)
    if week_files is not None:
        return ComputerIntent(
            calls=(_synthetic("list_this_week_files", week_files, "intent_week"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_this_week_files",
        )

    today_files = extract_today_files(text)
    if today_files is not None:
        return ComputerIntent(
            calls=(_synthetic("list_today_files", today_files, "intent_today"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_today_files",
        )

    oldest = extract_oldest_file(text)
    if oldest is not None:
        return ComputerIntent(
            calls=(_synthetic("get_oldest_file", oldest, "intent_oldest"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_oldest_file",
        )

    smallest = extract_smallest_file(text)
    if smallest is not None:
        return ComputerIntent(
            calls=(_synthetic("get_smallest_file", smallest, "intent_smallest"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_smallest_file",
        )

    newest = extract_newest_file(text)
    if newest is not None:
        return ComputerIntent(
            calls=(_synthetic("get_newest_file", newest, "intent_newest"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_newest_file",
        )

    recent = extract_recent_files(text)
    if recent is not None:
        return ComputerIntent(
            calls=(_synthetic("list_recent_files", recent, "intent_recent"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_recent_files",
        )

    file_info = extract_file_info(text)
    if file_info is not None:
        return ComputerIntent(
            calls=(_synthetic("get_file_info", file_info, "intent_file_info"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_file_info",
        )

    existed = extract_file_exists(text)
    if existed is not None:
        return ComputerIntent(
            calls=(_synthetic("file_exists", existed, "intent_exists"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="file_exists",
        )

    lined = extract_line_count(text)
    if lined is not None:
        return ComputerIntent(
            calls=(_synthetic("count_file_lines", lined, "intent_lines"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_file_lines",
        )

    copied_path = extract_copy_file_path(text)
    if copied_path is not None:
        return ComputerIntent(
            calls=(_synthetic("copy_file_path", copied_path, "intent_copy_path"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="copy_file_path",
        )

    folder_path = extract_special_folder_path(text)
    if folder_path is not None:
        return ComputerIntent(
            calls=(_synthetic("get_special_folder_path", folder_path, "intent_folder_path"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_special_folder_path",
        )

    largest = extract_largest_file(text)
    if largest is not None:
        return ComputerIntent(
            calls=(_synthetic("get_largest_file", largest, "intent_largest"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_largest_file",
        )

    folder_size = extract_folder_size(text)
    if folder_size is not None:
        return ComputerIntent(
            calls=(_synthetic("get_folder_size", folder_size, "intent_folder_size"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_folder_size",
        )

    if is_onedrive_path_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_onedrive_path", {}, "intent_onedrive"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_onedrive_path",
        )

    if is_temp_folder_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_temp_folder_path", {}, "intent_temp"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_temp_folder_path",
        )

    if is_user_profile_request(text):
        return ComputerIntent(
            calls=(_synthetic("get_user_profile_path", {}, "intent_profile"),),
            categories=frozenset({"system"}),
            summarize=True,
            reason="get_user_profile_path",
        )

    counted = extract_count_by_extension(text)
    if counted is not None:
        return ComputerIntent(
            calls=(_synthetic("count_files_by_extension", counted, "intent_count_ext"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_files_by_extension",
        )

    by_ext = extract_files_by_extension(text)
    if by_ext is not None:
        return ComputerIntent(
            calls=(_synthetic("list_files_by_extension", by_ext, "intent_by_ext"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_files_by_extension",
        )

    emptied = extract_directory_empty(text)
    if emptied is not None:
        return ComputerIntent(
            calls=(_synthetic("is_directory_empty", emptied, "intent_dir_empty"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="is_directory_empty",
        )

    folder_count = extract_count_subdirectories(text)
    if folder_count is not None:
        return ComputerIntent(
            calls=(_synthetic("count_subdirectories", folder_count, "intent_count_dirs"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="count_subdirectories",
        )

    subdirs = extract_subdirectories(text)
    if subdirs is not None:
        return ComputerIntent(
            calls=(_synthetic("list_subdirectories", subdirs, "intent_subdirs"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_subdirectories",
        )

    git_args = extract_git_status(text)
    if git_args is not None:
        return ComputerIntent(
            calls=(_synthetic("git_status", git_args, "intent_git"),),
            categories=frozenset({"git"}),
            summarize=True,
            reason="git_status",
        )

    renamed = extract_rename_file(text)
    if renamed is not None:
        return ComputerIntent(
            calls=(_synthetic("rename_file", renamed, "intent_rename"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="rename_file",
        )

    duplicated = extract_duplicate_file(text)
    if duplicated is not None:
        return ComputerIntent(
            calls=(_synthetic("duplicate_file", duplicated, "intent_dup"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="duplicate_file",
        )

    hashed = extract_file_hash(text)
    if hashed is not None:
        return ComputerIntent(
            calls=(_synthetic("get_file_hash", hashed, "intent_hash"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="get_file_hash",
        )

    read_path = extract_read_file(text)
    if read_path is not None:
        return ComputerIntent(
            calls=(_synthetic("read_file", read_path, "intent_read_file"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="read_file",
        )

    copied_moved = extract_copy_or_move(text)
    if copied_moved is not None:
        action, args = copied_moved
        return ComputerIntent(
            calls=(_synthetic(action, args, f"intent_{action}"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason=action,
        )

    folder = match_special_folder(text)
    if folder and tokens & _OPEN_TOKENS:
        return ComputerIntent(
            calls=(_synthetic("open_folder", {"path": folder}, "intent_open_folder"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="open_folder",
        )
    if folder and _LIST_HINT.search(text.casefold()):
        return ComputerIntent(
            calls=(_synthetic("list_directory", {"path": folder}, "intent_list_dir"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="list_directory",
        )
    file_search = extract_file_search(text)
    if file_search is not None:
        return ComputerIntent(
            calls=(_synthetic("search_files", file_search, "intent_search_files"),),
            categories=frozenset({"filesystem"}),
            summarize=True,
            reason="search_files",
        )

    settings_page = extract_windows_settings(text)
    if settings_page is not None:
        return ComputerIntent(
            calls=(_synthetic("open_windows_settings", settings_page, "intent_settings"),),
            categories=frozenset({"application"}),
            summarize=True,
            reason="open_windows_settings",
        )

    app = match_known_app(text)
    if app and is_bare_app_launch(text):
        if tokens & _CLOSE_TOKENS:
            return ComputerIntent(
                calls=(_synthetic("close_application", {"name": app}, "intent_close_app"),),
                categories=frozenset({"application"}),
                summarize=True,
                reason="close_application",
            )
        return ComputerIntent(
            calls=(_synthetic("open_application", {"name": app}, "intent_open_app"),),
            categories=frozenset({"application"}),
            summarize=True,
            reason="open_application",
        )

    if is_deixis_action(text) and not (tokens & _COPY_TOKENS):
        return ComputerIntent(
            calls=(
                _synthetic("get_selected_text", {}, "intent_deixis_selection"),
                _synthetic("get_foreground_window", {}, "intent_deixis_window"),
                _synthetic("clipboard_read", {}, "intent_deixis_clipboard"),
            ),
            categories=frozenset({"application", "system", "filesystem"}),
            summarize=False,
            reason="deixis_context",
        )

    return None
