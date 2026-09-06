"""Günlük Türkçe işlem niyeti — host araç yönlendirmesi."""

from __future__ import annotations

import json

from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import (
    _direct_action_response,
    _media_open_requested,
    _select_tool_categories,
)
from app.services.tools.intent import resolve_computer_intent
from app.services.tools.registry import ToolRegistry

def _call_name(intent, index: int = 0) -> str:
    return str(intent.calls[index]["function"]["name"])

def _call_args(intent, index: int = 0) -> dict:
    return json.loads(intent.calls[index]["function"]["arguments"])

def test_chrome_ac_open_application() -> None:
    intent = resolve_computer_intent("Chrome'u aç")
    assert intent is not None
    assert intent.reason == "open_application"
    assert _call_name(intent) == "open_application"
    assert _call_args(intent) == {"name": "chrome"}
    assert _select_tool_categories("Chrome'u aç") == {"application"}

def test_spotify_uygulama_web_aramasina_dusmez() -> None:
    assert _media_open_requested("Spotify'ı aç") is False
    assert _media_open_requested("Spotify uygulamasını aç") is False
    intent = resolve_computer_intent("Spotify'ı aç")
    assert intent is not None
    assert _call_name(intent) == "open_application"
    assert _call_args(intent)["name"] == "spotify"
    assert _media_open_requested("Manifest şarkısını Spotify'da aç") is True
    assert resolve_computer_intent("Manifest şarkısını Spotify'da aç") is None

def test_sunu_yap_secim_ve_pano_okur() -> None:
    intent = resolve_computer_intent("şunu yap")
    assert intent is not None
    assert intent.summarize is False
    assert [_call_name(intent, i) for i in range(3)] == [
        "get_selected_text",
        "get_foreground_window",
        "clipboard_read",
    ]
    assert _select_tool_categories("şunu yap") == {"application", "system", "filesystem"}

def test_sunu_panoya_yaz_secimi_kopyalar() -> None:
    intent = resolve_computer_intent("şunu panoya yaz")
    assert intent is not None
    assert _call_name(intent) == "copy_selected_text"

def test_sunu_kopyala_tek_arac() -> None:
    intent = resolve_computer_intent("şunu kopyala")
    assert intent is not None
    assert _call_name(intent) == "copy_selected_text"
    assert intent.summarize is True

def test_ses_ve_ekran_ve_klasor() -> None:
    volume = resolve_computer_intent("sesi yüzde 30 yap")
    assert volume is not None
    assert _call_args(volume) == {"level": 30}
    assert resolve_computer_intent("ekran görüntüsü al") is not None
    listed = resolve_computer_intent("masaüstündekileri listele")
    assert listed is not None
    assert _call_name(listed) == "list_directory"
    assert _call_args(listed) == {"path": "desktop"}
    opened = resolve_computer_intent("indirilenleri aç")
    assert opened is not None
    assert _call_name(opened) == "open_folder"
    assert _call_args(opened) == {"path": "downloads"}

def test_anlatma_sorusu_arac_uretmez() -> None:
    assert resolve_computer_intent("yarın ne yapmalıyım") is None
    assert resolve_computer_intent("açıklama yapar mısın") is None
    assert _select_tool_categories("yarın ne yapmalıyım") is None

def test_ses_oku_ve_panoya_yaz() -> None:
    volume = resolve_computer_intent("ses kaç")
    assert volume is not None
    assert _call_name(volume) == "get_volume"
    wrote = resolve_computer_intent("panoya yaz merhaba dünya")
    assert wrote is not None
    assert _call_name(wrote) == "clipboard_write"
    assert _call_args(wrote)["text"] == "merhaba dünya"
    cleared = resolve_computer_intent("panoyu temizle")
    assert cleared is not None
    assert _call_name(cleared) == "clipboard_clear"

def test_chrome_da_konu_web_aramasi() -> None:
    assert resolve_computer_intent("Chrome'u aç") is not None
    assert _call_name(resolve_computer_intent("Chrome'u aç")) == "open_application"
    lookup = resolve_computer_intent("Chrome'da wikipedia ara")
    assert lookup is not None
    assert _call_name(lookup) == "web_search"
    assert "wikipedia" in _call_args(lookup)["query"]
    assert resolve_computer_intent("Chrome'da youtube aç") is not None
    assert _call_name(resolve_computer_intent("Chrome'da youtube aç")) == "web_search"

def test_doviz_hesap_degil_fx() -> None:
    fx = resolve_computer_intent("dolar kaç TL")
    assert fx is not None
    assert _call_name(fx) == "fx_rate"
    assert _call_args(fx)["base"] == "USD"
    assert _call_args(fx)["quote"] == "TRY"
    assert _select_tool_categories("dolar kaç TL") == {"web"}
    crypto = resolve_computer_intent("bitcoin kaç dolar")
    assert crypto is not None
    assert _call_name(crypto) == "web_search"
    calc = resolve_computer_intent("2+2 kaç eder")
    assert calc is not None
    assert _call_name(calc) == "calculate"
    assert _call_args(calc)["expression"].replace(" ", "").startswith("2+2")
    units = resolve_computer_intent("100 km kaç mil")
    assert units is not None
    assert _call_args(units)["from_unit"].lower().startswith("km")
    assert _call_args(units)["to_unit"].lower().startswith("mil")

def test_wiki_niyeti() -> None:
    wiki = resolve_computer_intent("Atatürk kimdir")
    assert wiki is not None
    assert _call_name(wiki) == "wiki_lookup"
    assert "Atatürk" in _call_args(wiki)["title"] or "atatürk" in _call_args(wiki)["title"].casefold()
    chrome_wiki = resolve_computer_intent("Chrome'da wikipedia ara")
    assert chrome_wiki is not None
    assert _call_name(chrome_wiki) == "web_search"

def test_hava_niyeti() -> None:
    weather = resolve_computer_intent("İstanbul'da hava nasıl")
    assert weather is not None
    assert _call_name(weather) == "weather"
    assert "İstanbul" in _call_args(weather)["place"] or "istanbul" in _call_args(weather)[
        "place"
    ].casefold()

def test_dosya_ara_pil_geri_donusum() -> None:
    search = resolve_computer_intent("masaüstünde rapor.pdf ara")
    assert search is not None
    assert _call_name(search) == "search_files"
    assert _call_args(search)["root"] == "desktop"
    assert "rapor" in _call_args(search)["query"]
    power = resolve_computer_intent("pil durumu nedir")
    assert power is not None
    assert _call_name(power) == "get_power_status"
    recycle = resolve_computer_intent("geri dönüşüm kutusunu aç")
    assert recycle is not None
    assert _call_name(recycle) == "open_recycle_bin"
    loose = resolve_computer_intent("fatura.pdf dosyasını ara")
    assert loose is not None
    assert _call_name(loose) == "search_files"
    assert "fatura" in _call_args(loose)["query"]
    idle = resolve_computer_intent("kaç dakikadır boştayım göster")
    assert idle is not None
    assert _call_name(idle) == "get_idle_time"
    display = resolve_computer_intent("ekran çözünürlüğü nedir")
    assert display is not None
    assert _call_name(display) == "get_display_info"
    holidays = resolve_computer_intent("bu yıl resmi tatiller neler")
    assert holidays is not None
    assert _call_name(holidays) == "public_holidays"
    net = resolve_computer_intent("ip adresim nedir")
    assert net is not None
    assert _call_name(net) == "get_network_interfaces"

def test_sunu_oku_ve_gunluk_host() -> None:
    selected = resolve_computer_intent("şunu oku")
    assert selected is not None
    assert _call_name(selected) == "get_selected_text"
    assert resolve_computer_intent("ne seçili") is not None
    assert _call_name(resolve_computer_intent("ne seçili")) == "get_selected_text"
    assert _call_name(resolve_computer_intent("hangi pencere açık")) == "get_foreground_window"
    assert _call_name(resolve_computer_intent("çalışan programlar")) == "list_processes"
    assert _call_name(resolve_computer_intent("kurulu uygulamalar")) == (
        "list_installed_applications"
    )
    uptime = resolve_computer_intent("bilgisayar ne zamandır açık")
    assert uptime is not None
    assert _call_name(uptime) == "get_uptime"
    wifi = resolve_computer_intent("wifi adı nedir")
    assert wifi is not None
    assert _call_name(wifi) == "get_wifi_status"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"
    assert _call_name(resolve_computer_intent("ip adresim nedir")) == "get_network_interfaces"
    notify = resolve_computer_intent("bana bildir toplantı var")
    assert notify is not None
    assert _call_name(notify) == "notify_user"
    assert _call_args(notify)["body"] == "toplantı var"
    recent = resolve_computer_intent("son indirilenler")
    assert recent is not None
    assert _call_name(recent) == "list_recent_files"
    assert _call_args(recent)["path"] == "downloads"
    shown = resolve_computer_intent("indirilenlerde gezginde göster")
    assert shown is not None
    assert _call_name(shown) == "show_in_folder"
    created = resolve_computer_intent("masaüstünde arşiv klasörü oluştur")
    assert created is not None
    assert _call_name(created) == "create_directory"
    assert _call_args(created)["path"] == "desktop/arşiv"
    info = resolve_computer_intent("masaüstünde rapor.pdf boyutu nedir")
    assert info is not None
    assert _call_name(info) == "get_file_info"
    assert _call_args(info)["path"] == "desktop/rapor.pdf"
    aqi = resolve_computer_intent("İstanbul hava kalitesi")
    assert aqi is not None
    assert _call_name(aqi) == "air_quality"
    assert "İstanbul" in _call_args(aqi)["place"] or "stanbul" in _call_args(aqi)[
        "place"
    ].casefold()
    weather = resolve_computer_intent("İstanbul'da hava nasıl")
    assert weather is not None
    assert _call_name(weather) == "weather"
    clip = resolve_computer_intent("panoda ne yazıyor")
    assert clip is not None
    assert _call_name(clip) == "clipboard_read"
    assert resolve_computer_intent("indirilenleri aç") is not None
    assert _call_name(resolve_computer_intent("indirilenleri aç")) == "open_folder"
    assert _call_name(resolve_computer_intent("şunu yap")) == "get_selected_text"
    assert len(resolve_computer_intent("şunu yap").calls) == 3
    read = resolve_computer_intent("masaüstünde notlar.txt oku")
    assert read is not None
    assert _call_name(read) == "read_file"
    assert _call_args(read)["path"] == "desktop/notlar.txt"
    assert _call_name(resolve_computer_intent("şunu oku")) == "get_selected_text"
    moved = resolve_computer_intent("masaüstündeki rapor.pdf'i belgelere taşı")
    assert moved is not None
    assert _call_name(moved) == "move_file"
    assert _call_args(moved)["source"] == "desktop/rapor.pdf"
    assert _call_args(moved)["destination"] == "documents/rapor.pdf"
    copied = resolve_computer_intent("masaüstündeki rapor.pdf'i belgelere kopyala")
    assert copied is not None
    assert _call_name(copied) == "copy_file"
    dictionary = resolve_computer_intent("merhaba ne demek")
    assert dictionary is not None
    assert _call_name(dictionary) == "dict_lookup"
    assert _call_args(dictionary)["term"].casefold().startswith("merhaba")
    assert _call_name(resolve_computer_intent("Atatürk kimdir")) == "wiki_lookup"
    quakes = resolve_computer_intent("son depremler")
    assert quakes is not None
    assert _call_name(quakes) == "earthquakes"
    assert _call_args(quakes)["region"] == "tr"
    country = resolve_computer_intent("Türkiye'nin başkenti neresi")
    assert country is not None
    assert _call_name(country) == "country_info"
    prayer = resolve_computer_intent("İstanbul namaz vakitleri")
    assert prayer is not None
    assert _call_name(prayer) == "prayer_times"
    sun = resolve_computer_intent("İstanbul gün batımı")
    assert sun is not None
    assert _call_name(sun) == "sun_times"
    assert _call_name(resolve_computer_intent("İstanbul'da hava nasıl")) == "weather"
    chrome_quake = resolve_computer_intent("Chrome'da deprem ara")
    assert chrome_quake is not None
    assert _call_name(chrome_quake) == "web_search"

def test_sunu_kaydet_ve_not() -> None:
    saved = resolve_computer_intent("şunu kaydet")
    assert saved is not None
    assert _call_name(saved) == "save_selected_text"
    assert _call_args(saved)["source"] == "selection"
    assert _call_args(saved)["mode"] == "create"
    assert _call_args(saved)["folder"] == "desktop"
    desktop = resolve_computer_intent("şunu belgelere kaydet notlar.txt")
    assert desktop is not None
    assert _call_name(desktop) == "save_selected_text"
    assert _call_args(desktop)["path"] == "documents/notlar.txt"
    note = resolve_computer_intent("şunu not al")
    assert note is not None
    assert _call_name(note) == "save_selected_text"
    clip = resolve_computer_intent("panodakini kaydet")
    assert clip is not None
    assert _call_args(clip)["source"] == "clipboard"
    appended = resolve_computer_intent("şunu notlar.txt'ye ekle")
    assert appended is not None
    assert _call_name(appended) == "save_selected_text"
    assert _call_args(appended)["mode"] == "append"
    assert _call_args(appended)["path"] == "desktop/notlar.txt"
    created = resolve_computer_intent("yeni not toplantı saat 10")
    assert created is not None
    assert _call_name(created) == "create_file"
    assert "toplantı" in _call_args(created)["content"]
    assert _call_args(created)["path"].startswith("desktop/uryx-not-")
    assert _call_name(resolve_computer_intent("şunu oku")) == "get_selected_text"
    assert _call_name(resolve_computer_intent("şunu kopyala")) == "copy_selected_text"
    assert _call_name(resolve_computer_intent("şunu yap")) == "get_selected_text"
    assert _call_name(resolve_computer_intent("ekran görüntüsünü kaydet")) == "take_screenshot"
    assert resolve_computer_intent("bunu hatırla") is None
    dropped = resolve_computer_intent("şunu masaüstüne at")
    assert dropped is not None
    assert _call_name(dropped) == "save_selected_text"
    assert _call_args(dropped)["folder"] == "desktop"
    assert resolve_computer_intent("şunu at") is None or _call_name(
        resolve_computer_intent("şunu at")
    ) != "save_selected_text"
    postal = resolve_computer_intent("34000 posta kodu neresi")
    assert postal is not None
    assert _call_name(postal) == "postal_lookup"
    assert _call_args(postal)["code"] == "34000"
    disk = resolve_computer_intent("disk ne kadar dolu")
    assert disk is not None
    assert _call_name(disk) == "get_disk_usage"
    text = _direct_action_response(
        "şunu kaydet",
        [
            {
                "tool_name": "save_selected_text",
                "success": True,
                "result": {"saved": True, "path": "C:\\Users\\x\\Desktop\\a.txt"},
            }
        ],
    )
    assert text is not None
    assert "kaydettim" in text

def test_bilgisayar_pil_usb_ad_hash_link() -> None:
    assert _call_name(resolve_computer_intent("pil durumu nedir")) == "get_power_status"
    battery = resolve_computer_intent("pil yüzde kaç")
    assert battery is not None
    assert _call_name(battery) == "get_battery_level"
    info = resolve_computer_intent("bilgisayar adı nedir")
    assert info is not None
    assert _call_name(info) == "get_computer_info"
    usb = resolve_computer_intent("takılı usb var mı göster")
    assert usb is not None
    assert _call_name(usb) == "list_removable_drives"
    renamed = resolve_computer_intent("masaüstünde rapor.pdf'i ozet.pdf olarak adlandır")
    assert renamed is not None
    assert _call_name(renamed) == "rename_file"
    assert _call_args(renamed)["source"] == "desktop/rapor.pdf"
    assert _call_args(renamed)["name"] == "ozet.pdf"
    hashed = resolve_computer_intent("masaüstünde rapor.pdf sha256 nedir")
    assert hashed is not None
    assert _call_name(hashed) == "get_file_hash"
    listed = resolve_computer_intent("masaüstünde kaç dosya var")
    assert listed is not None
    assert _call_name(listed) == "list_directory"
    link = resolve_computer_intent("şu linki aç https://example.com/x")
    assert link is not None
    assert _call_name(link) == "open_external_url"
    assert "example.com" in _call_args(link)["url"]
    chrome = resolve_computer_intent("Chrome'da https://example.com aç")
    assert chrome is not None
    assert _call_name(chrome) == "web_search"
    assert _call_name(resolve_computer_intent("disk ne kadar dolu")) == "get_disk_usage"
    assert _call_name(resolve_computer_intent("şunu kaydet")) == "save_selected_text"
    installed = resolve_computer_intent("chrome yüklü mü")
    assert installed is not None
    assert _call_name(installed) == "list_installed_applications"
    assert _call_args(installed)["query"] == "chrome"
    printers = resolve_computer_intent("yazıcıları listele")
    assert printers is not None
    assert _call_name(printers) == "list_printers"
    dup = resolve_computer_intent("masaüstünde rapor.pdf dosyasını çoğalt")
    assert dup is not None
    assert _call_name(dup) == "duplicate_file"
    assert _call_args(dup)["path"] == "desktop/rapor.pdf"

def test_gunluk_host_pencere_yol_cop_git() -> None:
    running = resolve_computer_intent("chrome çalışıyor mu")
    assert running is not None
    assert _call_name(running) == "is_process_running"
    assert _call_args(running)["name"] == "chrome"
    assert _call_name(resolve_computer_intent("chrome yüklü mü")) == (
        "list_installed_applications"
    )
    assert _call_name(resolve_computer_intent("çalışan programlar")) == "list_processes"
    assert _call_name(resolve_computer_intent("hangi pencere açık")) == "get_foreground_window"
    windows = resolve_computer_intent("açık pencereleri listele")
    assert windows is not None
    assert _call_name(windows) == "list_open_windows"
    assert _call_name(resolve_computer_intent("kaç monitör var")) == "get_display_info"
    browser = resolve_computer_intent("varsayılan tarayıcı nedir")
    assert browser is not None
    assert _call_name(browser) == "get_default_browser"
    locale = resolve_computer_intent("sistem dili nedir")
    assert locale is not None
    assert _call_name(locale) == "get_system_locale"
    existed = resolve_computer_intent("masaüstünde rapor.pdf var mı")
    assert existed is not None
    assert _call_name(existed) == "file_exists"
    assert _call_args(existed)["path"] == "desktop/rapor.pdf"
    assert _call_name(resolve_computer_intent("masaüstünde kaç dosya var")) == "list_directory"
    lined = resolve_computer_intent("masaüstünde notlar.txt kaç satır")
    assert lined is not None
    assert _call_name(lined) == "count_file_lines"
    copied = resolve_computer_intent("masaüstünde rapor.pdf yolunu kopyala")
    assert copied is not None
    assert _call_name(copied) == "copy_file_path"
    assert _call_name(resolve_computer_intent("şunu kopyala")) == "copy_selected_text"
    settings = resolve_computer_intent("bluetooth ayarlarını aç")
    assert settings is not None
    assert _call_name(settings) == "open_windows_settings"
    assert _call_args(settings)["page"] == "bluetooth"
    bare_settings = resolve_computer_intent("ayarlar aç")
    assert bare_settings is not None
    assert _call_name(bare_settings) == "open_application"
    assert _call_args(bare_settings)["name"] == "settings"
    ejected = resolve_computer_intent("E sürücüsünü çıkar")
    assert ejected is not None
    assert _call_name(ejected) == "eject_removable_drive"
    assert _call_args(ejected)["letter"] == "E"
    assert _call_name(resolve_computer_intent("takılı usb var mı göster")) == (
        "list_removable_drives"
    )
    trashed = resolve_computer_intent("masaüstünde rapor.pdf'i çöpe at")
    assert trashed is not None
    assert _call_name(trashed) == "delete_file"
    assert _call_args(trashed)["path"] == "desktop/rapor.pdf"
    assert resolve_computer_intent("geri dönüşüm kutusunu boşalt") is None or _call_name(
        resolve_computer_intent("geri dönüşüm kutusunu boşalt")
    ) != "delete_file"
    assert _call_name(resolve_computer_intent("geri dönüşüm kutusunu aç")) == "open_recycle_bin"
    git = resolve_computer_intent("masaüstünde Uryx_v2 git durumu")
    assert git is not None
    assert _call_name(git) == "git_status"
    assert _call_args(git)["path"] == "desktop/Uryx_v2"
    text = _direct_action_response(
        "chrome çalışıyor mu",
        [
            {
                "tool_name": "is_process_running",
                "success": True,
                "result": {"running": True, "name": "chrome"},
            }
        ],
    )
    assert text is not None
    assert "çalışıyor" in text

def test_saat_internet_cop_klasor_surucu() -> None:
    clock = resolve_computer_intent("saat kaç")
    assert clock is not None
    assert _call_name(clock) == "get_system_time"
    assert _call_name(resolve_computer_intent("bugünün tarihi nedir")) == "get_system_time"
    assert _call_name(resolve_computer_intent("İstanbul namaz saatleri")) == "prayer_times"
    dark = resolve_computer_intent("karanlık mod açık mı")
    assert dark is not None
    assert _call_name(dark) == "get_dark_mode"
    net = resolve_computer_intent("internet var mı")
    assert net is not None
    assert _call_name(net) == "get_internet_status"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"
    assert _call_name(resolve_computer_intent("ip adresim nedir")) == "get_network_interfaces"
    startup = resolve_computer_intent("başlangıç programlarını listele")
    assert startup is not None
    assert _call_name(startup) == "list_startup_apps"
    drives = resolve_computer_intent("sürücüleri listele")
    assert drives is not None
    assert _call_name(drives) == "list_logical_drives"
    assert _call_name(resolve_computer_intent("takılı usb var mı göster")) == (
        "list_removable_drives"
    )
    assert _call_name(resolve_computer_intent("disk ne kadar dolu")) == "get_disk_usage"
    recycle = resolve_computer_intent("çöpte kaç öğe var")
    assert recycle is not None
    assert _call_name(recycle) == "get_recycle_bin_info"
    assert _call_name(resolve_computer_intent("geri dönüşüm kutusunu aç")) == "open_recycle_bin"
    assert resolve_computer_intent("geri dönüşüm kutusunu boşalt") is None or _call_name(
        resolve_computer_intent("geri dönüşüm kutusunu boşalt")
    ) not in {"get_recycle_bin_info", "delete_file"}
    folder = resolve_computer_intent("masaüstü yolu nedir")
    assert folder is not None
    assert _call_name(folder) == "get_special_folder_path"
    assert _call_args(folder)["folder"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstünde rapor.pdf yolunu kopyala")) == (
        "copy_file_path"
    )
    sized = resolve_computer_intent("masaüstü ne kadar yer kaplıyor")
    assert sized is not None
    assert _call_name(sized) == "get_folder_size"
    assert _call_args(sized)["path"] == "desktop"
    located = resolve_computer_intent("chrome nerede kurulu")
    assert located is not None
    assert _call_name(located) == "resolve_application_path"
    assert _call_args(located)["name"] == "chrome"
    assert _call_name(resolve_computer_intent("chrome yüklü mü")) == (
        "list_installed_applications"
    )
    assert _call_name(resolve_computer_intent("chrome çalışıyor mu")) == "is_process_running"
    assert _call_name(resolve_computer_intent("Chrome'u aç")) == "open_application"

def test_yazici_pdf_wifi_yeni_dosya() -> None:
    printer = resolve_computer_intent("varsayılan yazıcı nedir")
    assert printer is not None
    assert _call_name(printer) == "get_default_printer"
    assert _call_name(resolve_computer_intent("yazıcıları listele")) == "list_printers"
    assoc = resolve_computer_intent("pdf'i hangi program açar")
    assert assoc is not None
    assert _call_name(assoc) == "get_file_association"
    assert _call_args(assoc)["extension"] == "pdf"
    listed = resolve_computer_intent("masaüstündeki pdf'leri listele")
    assert listed is not None
    assert _call_name(listed) == "list_files_by_extension"
    assert _call_args(listed)["extension"] == "pdf"
    assert _call_args(listed)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstünde kaç dosya var")) == "list_directory"
    newest = resolve_computer_intent("en son indirilen dosya nedir")
    assert newest is not None
    assert _call_name(newest) == "get_newest_file"
    assert _call_args(newest)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("son indirilenler")) == "list_recent_files"
    empty = resolve_computer_intent("masaüstü boş mu")
    assert empty is not None
    assert _call_name(empty) == "is_directory_empty"
    profile = resolve_computer_intent("kullanıcı klasörüm nerede")
    assert profile is not None
    assert _call_name(profile) == "get_user_profile_path"
    assert _call_name(resolve_computer_intent("masaüstü yolu nedir")) == "get_special_folder_path"
    plan = resolve_computer_intent("güç planı nedir")
    assert plan is not None
    assert _call_name(plan) == "get_power_plan"
    assert _call_name(resolve_computer_intent("pil durumu nedir")) == "get_power_status"
    nearby = resolve_computer_intent("yakındaki wifi ağlarını listele")
    assert nearby is not None
    assert _call_name(nearby) == "list_nearby_wifi"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"

def test_en_buyuk_kac_pdf_klasor_boot_model() -> None:
    largest = resolve_computer_intent("masaüstünde en büyük dosya")
    assert largest is not None
    assert _call_name(largest) == "get_largest_file"
    assert _call_args(largest)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstü ne kadar yer kaplıyor")) == "get_folder_size"
    assert _call_name(resolve_computer_intent("en son indirilen dosya nedir")) == "get_newest_file"
    counted = resolve_computer_intent("masaüstünde kaç pdf var")
    assert counted is not None
    assert _call_name(counted) == "count_files_by_extension"
    assert _call_args(counted)["extension"] == "pdf"
    assert _call_args(counted)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstünde kaç dosya var")) == "list_directory"
    assert _call_name(resolve_computer_intent("masaüstündeki pdf'leri listele")) == (
        "list_files_by_extension"
    )
    folders = resolve_computer_intent("masaüstündeki klasörleri listele")
    assert folders is not None
    assert _call_name(folders) == "list_subdirectories"
    assert _call_args(folders)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstündekileri listele")) == "list_directory"
    today = resolve_computer_intent("bugün indirilenler")
    assert today is not None
    assert _call_name(today) == "list_today_files"
    assert _call_args(today)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("son indirilenler")) == "list_recent_files"
    assert _call_name(resolve_computer_intent("en son indirilen dosya")) == "get_newest_file"
    boot = resolve_computer_intent("son açılış ne zaman")
    assert boot is not None
    assert _call_name(boot) == "get_last_boot_time"
    assert _call_name(resolve_computer_intent("bilgisayar ne zamandır açık")) == "get_uptime"
    model = resolve_computer_intent("bilgisayar modeli nedir")
    assert model is not None
    assert _call_name(model) == "get_system_model"
    assert _call_name(resolve_computer_intent("bilgisayar adı nedir")) == "get_computer_info"
    night = resolve_computer_intent("gece ışığı açık mı")
    assert night is not None
    assert _call_name(night) == "get_night_light"
    assert _call_name(resolve_computer_intent("karanlık mod açık mı")) == "get_dark_mode"
    bt = resolve_computer_intent("bluetooth açık mı")
    assert bt is not None
    assert _call_name(bt) == "get_bluetooth_status"
    assert _call_name(resolve_computer_intent("bluetooth ayarlarını aç")) == (
        "open_windows_settings"
    )

def test_eski_kac_klasor_dilim_wifi_radyo() -> None:
    oldest = resolve_computer_intent("masaüstünde en eski dosya")
    assert oldest is not None
    assert _call_name(oldest) == "get_oldest_file"
    assert _call_args(oldest)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstünde en büyük dosya")) == "get_largest_file"
    assert _call_name(resolve_computer_intent("en son indirilen dosya")) == "get_newest_file"
    counted = resolve_computer_intent("masaüstünde kaç klasör var")
    assert counted is not None
    assert _call_name(counted) == "count_subdirectories"
    assert _call_args(counted)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstündeki klasörleri listele")) == (
        "list_subdirectories"
    )
    assert _call_name(resolve_computer_intent("masaüstünde kaç dosya var")) == "list_directory"
    assert _call_name(resolve_computer_intent("saat dilimi nedir")) == "get_timezone"
    assert _call_name(resolve_computer_intent("saat kaç")) == "get_system_time"
    assert _call_name(resolve_computer_intent("geçici klasör nerede")) == "get_temp_folder_path"
    assert _call_name(resolve_computer_intent("kullanıcı klasörüm nerede")) == (
        "get_user_profile_path"
    )
    assert _call_name(resolve_computer_intent("duvar kağıdı nedir")) == "get_wallpaper_path"
    assert _call_name(resolve_computer_intent("wifi açık mı")) == "get_wifi_radio"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"
    assert _call_name(resolve_computer_intent("yakındaki wifi ağlarını listele")) == (
        "list_nearby_wifi"
    )
    assert _call_name(resolve_computer_intent("hangi hoparlör")) == "get_default_playback_device"
    assert _call_name(resolve_computer_intent("ses kaç")) == "get_volume"
    labeled = resolve_computer_intent("C sürücüsünün adı nedir")
    assert labeled is not None
    assert _call_name(labeled) == "get_drive_label"
    assert _call_args(labeled)["letter"] == "C"
    assert _call_name(resolve_computer_intent("sürücüleri listele")) == "list_logical_drives"

def test_kucuk_hafta_onedrive_cpu_mic() -> None:
    smallest = resolve_computer_intent("masaüstünde en küçük dosya")
    assert smallest is not None
    assert _call_name(smallest) == "get_smallest_file"
    assert _call_args(smallest)["path"] == "desktop"
    assert _call_name(resolve_computer_intent("masaüstünde en büyük dosya")) == "get_largest_file"
    assert _call_name(resolve_computer_intent("masaüstünde en eski dosya")) == "get_oldest_file"
    week = resolve_computer_intent("bu hafta indirilenler")
    assert week is not None
    assert _call_name(week) == "list_this_week_files"
    assert _call_args(week)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("bugün indirilenler")) == "list_today_files"
    assert _call_name(resolve_computer_intent("son indirilenler")) == "list_recent_files"
    assert _call_name(resolve_computer_intent("onedrive klasör yolu")) == "get_onedrive_path"
    assert _call_name(resolve_computer_intent("kullanıcı klasörüm nerede")) == (
        "get_user_profile_path"
    )
    assert _call_name(resolve_computer_intent("işlemci adı nedir")) == "get_cpu_name"
    assert _call_name(resolve_computer_intent("işlemci kullanımı nedir")) == "get_cpu_usage"
    assert _call_name(resolve_computer_intent("ekran kartı adı nedir")) == "get_gpu_name"
    assert _call_name(resolve_computer_intent("ekran kartı kullanımı")) == "get_gpu_usage"
    assert _call_name(resolve_computer_intent("ethernet bağlı mı")) == "get_ethernet_status"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"
    assert _call_name(resolve_computer_intent("hangi mikrofon")) == "get_default_recording_device"
    assert _call_name(resolve_computer_intent("hangi hoparlör")) == "get_default_playback_device"
    assert _call_name(resolve_computer_intent("yenileme hızı nedir")) == "get_refresh_rate"
    assert _call_name(resolve_computer_intent("kaç monitör var")) == "get_display_info"

def test_dun_olcek_cekirdek_ucak() -> None:
    yesterday = resolve_computer_intent("dün indirilenler")
    assert yesterday is not None
    assert _call_name(yesterday) == "list_yesterday_files"
    assert _call_args(yesterday)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("bugün indirilenler")) == "list_today_files"
    assert _call_name(resolve_computer_intent("bu hafta indirilenler")) == "list_this_week_files"
    counted = resolve_computer_intent("bugün kaç dosya indirildi")
    assert counted is not None
    assert _call_name(counted) == "count_today_files"
    assert _call_args(counted)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("masaüstünde kaç dosya var")) == "list_directory"
    assert _call_name(resolve_computer_intent("ekran ölçeği nedir")) == "get_screen_scale"
    assert _call_name(resolve_computer_intent("yenileme hızı nedir")) == "get_refresh_rate"
    assert _call_name(resolve_computer_intent("kaç monitör var")) == "get_display_info"
    assert _call_name(resolve_computer_intent("kaç GB ram var")) == "get_ram_size"
    assert _call_name(resolve_computer_intent("RAM kullanımı nedir")) == "get_ram_usage"
    assert _call_name(resolve_computer_intent("kaç çekirdek")) == "get_cpu_count"
    assert _call_name(resolve_computer_intent("işlemci adı nedir")) == "get_cpu_name"
    assert _call_name(resolve_computer_intent("ses kapalı mı")) == "get_mute_status"
    assert _call_name(resolve_computer_intent("ses kaç")) == "get_volume"
    assert _call_name(resolve_computer_intent("sessiz ol")) == "set_volume"
    filesystem = resolve_computer_intent("C dosya sistemi nedir")
    assert filesystem is not None
    assert _call_name(filesystem) == "get_drive_filesystem"
    assert _call_args(filesystem)["letter"] == "C"
    assert _call_name(resolve_computer_intent("C sürücüsünün adı")) == "get_drive_label"
    assert _call_name(resolve_computer_intent("uçak modu açık mı")) == "get_airplane_mode"
    assert _call_name(resolve_computer_intent("wifi açık mı")) == "get_wifi_radio"

def test_ay_vpn_parlaklik_klavye() -> None:
    month = resolve_computer_intent("bu ay indirilenler")
    assert month is not None
    assert _call_name(month) == "list_this_month_files"
    assert _call_args(month)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("bu hafta indirilenler")) == "list_this_week_files"
    assert _call_name(resolve_computer_intent("dün indirilenler")) == "list_yesterday_files"
    counted = resolve_computer_intent("dün kaç dosya indirildi")
    assert counted is not None
    assert _call_name(counted) == "count_yesterday_files"
    assert _call_args(counted)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("bugün kaç dosya indirildi")) == "count_today_files"
    assert _call_name(resolve_computer_intent("windows sürümü nedir")) == "get_os_version"
    assert _call_name(resolve_computer_intent("bilgisayar adı nedir")) == "get_computer_info"
    assert _call_name(resolve_computer_intent("kullanıcı adım ne")) == "get_username"
    assert _call_name(resolve_computer_intent("kullanıcı klasörüm nerede")) == (
        "get_user_profile_path"
    )
    assert _call_name(resolve_computer_intent("parlaklık kaç")) == "get_brightness"
    assert _call_name(resolve_computer_intent("ekran ölçeği nedir")) == "get_screen_scale"
    assert _call_name(resolve_computer_intent("gece ışığı açık mı")) == "get_night_light"
    assert _call_name(resolve_computer_intent("vpn bağlı mı")) == "get_vpn_status"
    assert _call_name(resolve_computer_intent("wifi açık mı")) == "get_wifi_radio"
    assert _call_name(resolve_computer_intent("klavye dili nedir")) == "get_keyboard_layout"
    assert _call_name(resolve_computer_intent("sistem dili nedir")) == "get_system_locale"
    assert _call_name(resolve_computer_intent("pil tasarrufu açık mı")) == "get_battery_saver"
    assert _call_name(resolve_computer_intent("pil yüzde kaç")) == "get_battery_level"

def test_hafta_sinyal_guvenlik_posta() -> None:
    week = resolve_computer_intent("bu hafta kaç dosya indirildi")
    assert week is not None
    assert _call_name(week) == "count_this_week_files"
    assert _call_args(week)["path"] == "downloads"
    assert _call_name(resolve_computer_intent("bu hafta indirilenler")) == "list_this_week_files"
    month = resolve_computer_intent("bu ay kaç dosya indirildi")
    assert month is not None
    assert _call_name(month) == "count_this_month_files"
    assert _call_name(resolve_computer_intent("bu ay indirilenler")) == "list_this_month_files"
    assert _call_name(resolve_computer_intent("64 bit mi")) == "get_architecture"
    assert _call_name(resolve_computer_intent("windows sürümü nedir")) == "get_os_version"
    assert _call_name(resolve_computer_intent("odaklanma yardımı açık mı")) == "get_focus_assist"
    assert _call_name(resolve_computer_intent("ses kapalı mı")) == "get_mute_status"
    assert _call_name(resolve_computer_intent("güvenlik duvarı açık mı")) == "get_firewall_status"
    assert _call_name(resolve_computer_intent("hangi e-posta uygulaması")) == "get_default_mail_app"
    assert _call_name(resolve_computer_intent("varsayılan tarayıcı nedir")) == "get_default_browser"
    assert _call_name(resolve_computer_intent("ekran görüntüleri klasörü nerede")) == (
        "get_screenshots_folder"
    )
    assert _call_name(resolve_computer_intent("ekran görüntüsü al")) == "take_screenshot"
    assert _call_name(resolve_computer_intent("wifi sinyal kaç")) == "get_wifi_signal"
    assert _call_name(resolve_computer_intent("wifi açık mı")) == "get_wifi_radio"
    assert _call_name(resolve_computer_intent("hangi ağa bağlıyım")) == "get_wifi_status"

def test_hesap_kategorisi_uygulama_ile_karismaz() -> None:
    assert _select_tool_categories("100 km kaç mil") == {"system"}
    assert _select_tool_categories("2+2 kaç eder") == {"system"}
    assert _select_tool_categories("hesap makinesini aç") == {"application"}

def test_yeni_host_araclar_kayitli_ve_onayli() -> None:
    registry = ToolRegistry()
    for name in (
        "list_directory",
        "copy_file",
        "copy_selected_text",
        "get_volume",
        "lock_workstation",
        "clipboard_clear",
        "get_power_status",
        "open_recycle_bin",
        "get_uptime",
        "get_wifi_status",
        "create_directory",
        "list_recent_files",
        "show_in_folder",
        "move_file",
        "get_file_info",
        "save_selected_text",
        "get_battery_level",
        "get_computer_info",
        "list_removable_drives",
        "rename_file",
        "get_file_hash",
        "open_external_url",
        "list_printers",
        "duplicate_file",
        "file_exists",
        "copy_file_path",
        "count_file_lines",
        "is_process_running",
        "list_open_windows",
        "get_system_locale",
        "get_default_browser",
        "eject_removable_drive",
        "open_windows_settings",
        "get_system_time",
        "get_dark_mode",
        "get_internet_status",
        "list_startup_apps",
        "list_logical_drives",
        "get_recycle_bin_info",
        "get_special_folder_path",
        "get_folder_size",
        "resolve_application_path",
        "get_default_printer",
        "get_file_association",
        "get_power_plan",
        "get_user_profile_path",
        "list_nearby_wifi",
        "list_files_by_extension",
        "get_newest_file",
        "is_directory_empty",
        "get_largest_file",
        "count_files_by_extension",
        "list_subdirectories",
        "list_today_files",
        "get_last_boot_time",
        "get_system_model",
        "get_night_light",
        "get_bluetooth_status",
        "get_oldest_file",
        "count_subdirectories",
        "get_timezone",
        "get_temp_folder_path",
        "get_wallpaper_path",
        "get_wifi_radio",
        "get_default_playback_device",
        "get_drive_label",
        "get_smallest_file",
        "list_this_week_files",
        "get_onedrive_path",
        "get_cpu_name",
        "get_gpu_name",
        "get_ethernet_status",
        "get_default_recording_device",
        "get_refresh_rate",
        "list_yesterday_files",
        "count_today_files",
        "get_screen_scale",
        "get_ram_size",
        "get_cpu_count",
        "get_mute_status",
        "get_drive_filesystem",
        "get_airplane_mode",
        "list_this_month_files",
        "count_yesterday_files",
        "get_os_version",
        "get_username",
        "get_brightness",
        "get_vpn_status",
        "get_keyboard_layout",
        "get_battery_saver",
        "count_this_week_files",
        "count_this_month_files",
        "get_architecture",
        "get_focus_assist",
        "get_firewall_status",
        "get_default_mail_app",
        "get_screenshots_folder",
        "get_wifi_signal",
    ):
        tool = registry.get(name)
        assert tool.execution is ExecutionTarget.HOST, name
    assert registry.get("list_directory").risk is RiskLevel.LOW
    assert registry.get("copy_selected_text").risk is RiskLevel.LOW
    assert registry.get("copy_file").risk is RiskLevel.MEDIUM
    assert registry.get("lock_workstation").risk is RiskLevel.MEDIUM
    assert registry.get("get_power_status").risk is RiskLevel.LOW
    assert registry.get("clipboard_clear").risk is RiskLevel.LOW
    assert registry.get("open_recycle_bin").risk is RiskLevel.LOW
    assert registry.get("get_uptime").risk is RiskLevel.LOW
    assert registry.get("get_wifi_status").risk is RiskLevel.LOW
    assert registry.get("create_directory").risk is RiskLevel.LOW
    assert registry.get("move_file").risk is RiskLevel.MEDIUM
    assert registry.get("save_selected_text").risk is RiskLevel.MEDIUM
    assert registry.get("get_battery_level").risk is RiskLevel.LOW
    assert registry.get("rename_file").risk is RiskLevel.MEDIUM
    assert registry.get("get_file_hash").risk is RiskLevel.LOW
    assert registry.get("open_external_url").risk is RiskLevel.LOW
    assert registry.requires_confirmation("rename_file", confirmation_enabled=True) is True
    assert registry.requires_confirmation("get_battery_level") is False
    assert registry.requires_confirmation("list_directory") is False
    assert registry.requires_confirmation("lock_workstation", confirmation_enabled=True) is True
    assert registry.requires_confirmation("open_recycle_bin") is False
    assert registry.requires_confirmation("save_selected_text", confirmation_enabled=True) is True
    assert registry.requires_confirmation("save_selected_text", confirmation_enabled=False) is False
    assert registry.get("file_exists").risk is RiskLevel.LOW
    assert registry.get("copy_file_path").risk is RiskLevel.LOW
    assert registry.get("count_file_lines").risk is RiskLevel.LOW
    assert registry.get("is_process_running").risk is RiskLevel.LOW
    assert registry.get("list_open_windows").risk is RiskLevel.LOW
    assert registry.get("get_system_locale").risk is RiskLevel.LOW
    assert registry.get("get_default_browser").risk is RiskLevel.LOW
    assert registry.get("open_windows_settings").risk is RiskLevel.LOW
    assert registry.get("eject_removable_drive").risk is RiskLevel.MEDIUM
    assert registry.requires_confirmation("eject_removable_drive", confirmation_enabled=True) is True
    assert registry.requires_confirmation("file_exists") is False
    assert registry.requires_confirmation("delete_file", confirmation_enabled=True) is True
    assert registry.get("get_system_time").risk is RiskLevel.LOW
    assert registry.get("get_recycle_bin_info").risk is RiskLevel.LOW
    assert registry.get("get_folder_size").risk is RiskLevel.LOW
    assert registry.requires_confirmation("get_recycle_bin_info") is False
    assert registry.get("get_default_printer").risk is RiskLevel.LOW
    assert registry.get("list_nearby_wifi").risk is RiskLevel.LOW
    assert registry.get("get_newest_file").risk is RiskLevel.LOW
    assert registry.requires_confirmation("list_files_by_extension") is False
    assert registry.get("get_largest_file").risk is RiskLevel.LOW
    assert registry.get("count_files_by_extension").risk is RiskLevel.LOW
    assert registry.get("list_subdirectories").risk is RiskLevel.LOW
    assert registry.get("list_today_files").risk is RiskLevel.LOW
    assert registry.get("get_last_boot_time").risk is RiskLevel.LOW
    assert registry.get("get_system_model").risk is RiskLevel.LOW
    assert registry.get("get_night_light").risk is RiskLevel.LOW
    assert registry.get("get_bluetooth_status").risk is RiskLevel.LOW
    assert registry.requires_confirmation("get_largest_file") is False
    assert registry.get("get_oldest_file").risk is RiskLevel.LOW
    assert registry.get("count_subdirectories").risk is RiskLevel.LOW
    assert registry.get("get_timezone").risk is RiskLevel.LOW
    assert registry.get("get_temp_folder_path").risk is RiskLevel.LOW
    assert registry.get("get_wallpaper_path").risk is RiskLevel.LOW
    assert registry.get("get_wifi_radio").risk is RiskLevel.LOW
    assert registry.get("get_default_playback_device").risk is RiskLevel.LOW
    assert registry.get("get_drive_label").risk is RiskLevel.LOW
    assert registry.requires_confirmation("get_oldest_file") is False
    assert registry.get("get_smallest_file").risk is RiskLevel.LOW
    assert registry.get("list_this_week_files").risk is RiskLevel.LOW
    assert registry.get("get_onedrive_path").risk is RiskLevel.LOW
    assert registry.get("get_cpu_name").risk is RiskLevel.LOW
    assert registry.get("get_gpu_name").risk is RiskLevel.LOW
    assert registry.get("get_ethernet_status").risk is RiskLevel.LOW
    assert registry.get("get_default_recording_device").risk is RiskLevel.LOW
    assert registry.get("get_refresh_rate").risk is RiskLevel.LOW
    assert registry.requires_confirmation("get_smallest_file") is False
    assert registry.get("list_yesterday_files").risk is RiskLevel.LOW
    assert registry.get("count_today_files").risk is RiskLevel.LOW
    assert registry.get("get_screen_scale").risk is RiskLevel.LOW
    assert registry.get("get_ram_size").risk is RiskLevel.LOW
    assert registry.get("get_cpu_count").risk is RiskLevel.LOW
    assert registry.get("get_mute_status").risk is RiskLevel.LOW
    assert registry.get("get_drive_filesystem").risk is RiskLevel.LOW
    assert registry.get("get_airplane_mode").risk is RiskLevel.LOW
    assert registry.requires_confirmation("list_yesterday_files") is False
    assert registry.requires_confirmation("get_airplane_mode") is False
    assert registry.get("list_this_month_files").risk is RiskLevel.LOW
    assert registry.get("count_yesterday_files").risk is RiskLevel.LOW
    assert registry.get("get_os_version").risk is RiskLevel.LOW
    assert registry.get("get_username").risk is RiskLevel.LOW
    assert registry.get("get_brightness").risk is RiskLevel.LOW
    assert registry.get("get_vpn_status").risk is RiskLevel.LOW
    assert registry.get("get_keyboard_layout").risk is RiskLevel.LOW
    assert registry.get("get_battery_saver").risk is RiskLevel.LOW
    assert registry.requires_confirmation("list_this_month_files") is False
    assert registry.requires_confirmation("get_vpn_status") is False
    assert registry.get("count_this_week_files").risk is RiskLevel.LOW
    assert registry.get("count_this_month_files").risk is RiskLevel.LOW
    assert registry.get("get_architecture").risk is RiskLevel.LOW
    assert registry.get("get_focus_assist").risk is RiskLevel.LOW
    assert registry.get("get_firewall_status").risk is RiskLevel.LOW
    assert registry.get("get_default_mail_app").risk is RiskLevel.LOW
    assert registry.get("get_screenshots_folder").risk is RiskLevel.LOW
    assert registry.get("get_wifi_signal").risk is RiskLevel.LOW
    assert registry.requires_confirmation("count_this_week_files") is False
    assert registry.requires_confirmation("get_wifi_signal") is False

def test_list_directory_ozeti() -> None:
    text = _direct_action_response(
        "masaüstündekileri listele",
        [
            {
                "tool_name": "list_directory",
                "success": True,
                "result": {"path": "C:\\Users\\x\\Desktop", "count": 4},
            }
        ],
    )
    assert text is not None
    assert "4" in text

def test_hesap_ve_ses_ozeti() -> None:
    calc = _direct_action_response(
        "2+2 kaç eder",
        [{"tool_name": "calculate", "success": True, "result": {"result": 4}}],
    )
    assert calc is not None
    assert "4" in calc
    heard = _direct_action_response(
        "ses kaç",
        [{"tool_name": "get_volume", "success": True, "result": {"volume": 42}}],
    )
    assert heard is not None
    assert "42" in heard
    hours = _direct_action_response(
        "bilgisayar ne zamandır açık",
        [{"tool_name": "get_uptime", "success": True, "result": {"uptime_hours": 3.5}}],
    )
    assert hours is not None
    assert "3.5" in hours
    wifi = _direct_action_response(
        "wifi adı nedir",
        [
            {
                "tool_name": "get_wifi_status",
                "success": True,
                "result": {"connected": True, "ssid": "EvAgi"},
            }
        ],
    )
    assert wifi is not None
    assert "EvAgi" in wifi

def test_takvim_ajanda_outlook_gorev_listesi_ayri() -> None:
    assert _call_name(resolve_computer_intent("takvimim")) == "list_calendar_events"
    assert _call_name(resolve_computer_intent("randevularım")) == "list_calendar_events"
    assert _call_name(resolve_computer_intent("ajanda")) == "list_calendar_events"
    processes = resolve_computer_intent("görev listesi")
    assert processes is not None
    assert _call_name(processes) == "list_processes"
    assert _call_name(processes) != "list_outlook_tasks"
    outlook_tasks = resolve_computer_intent("outlook görevlerim")
    assert outlook_tasks is not None
    assert _call_name(outlook_tasks) == "list_outlook_tasks"

def test_thread_ve_ucakta_negatif_intent() -> None:
    thread = resolve_computer_intent("kaç thread")
    thread_count = resolve_computer_intent("thread sayısı")
    if thread is not None:
        assert _call_name(thread) != "get_cpu_count"
    if thread_count is not None:
        assert _call_name(thread_count) != "get_cpu_count"
    travel = resolve_computer_intent("uçakta mıyım")
    if travel is not None:
        assert _call_name(travel) != "get_airplane_mode"
    assert _call_name(resolve_computer_intent("kaç çekirdek")) == "get_cpu_count"
    assert _call_name(resolve_computer_intent("uçak modu açık mı")) == "get_airplane_mode"
