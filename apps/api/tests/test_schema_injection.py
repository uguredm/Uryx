"""Kategorili turlar çekirdek 8'e sıkışmaz — host/dosya/haber/wiki şeması gelir."""

from __future__ import annotations

from app.services.chat.orchestrator import (
    CORE_EVERYDAY_TOOLS,
    _select_tool_categories,
    prepare_tool_schemas,
)
from app.services.tools.registry import ToolRegistry

def _names(message: str) -> set[str]:
    return {item["function"]["name"] for item in prepare_tool_schemas(message, ToolRegistry())}

def test_belirsiz_tur_cekirdek_8_kalir() -> None:
    names = _names("yarın ne yapmalıyım")
    assert names == set(CORE_EVERYDAY_TOOLS)
    assert _select_tool_categories("yarın ne yapmalıyım") is None

def test_chrome_ac_uygulama_semasi() -> None:
    cats = _select_tool_categories("Chrome'u aç")
    assert cats is not None
    assert "application" in cats
    names = _names("Chrome'u aç")
    assert "open_application" in names
    assert "close_application" in names
    assert names != set(CORE_EVERYDAY_TOOLS)
    assert "iss_now" not in names

def test_klasor_ve_dosya_semasi() -> None:
    listed = _names("masaüstündekileri listele")
    assert "list_directory" in listed
    assert listed != set(CORE_EVERYDAY_TOOLS)
    opened = _names("indirilenleri aç")
    assert "open_folder" in opened
    assert "open_folder" not in CORE_EVERYDAY_TOOLS

def test_haber_ve_wiki_semasi() -> None:
    news = _names("Ankara gündem haberleri")
    assert "web_news" in news
    assert "web_research" in news
    assert "wiki_lookup" not in news
    assert news != set(CORE_EVERYDAY_TOOLS)
    wiki = _names("İstanbul wikipedia maddesi")
    assert "wiki_lookup" in wiki
    assert "web_search" in wiki
    assert "web_news" not in wiki
    kimdir = _names("Atatürk kimdir")
    assert "wiki_lookup" in kimdir

def test_host_ses_ve_web_kur() -> None:
    volume = _names("ses kaç")
    assert "get_volume" in volume
    assert "set_volume" in volume
    assert volume != set(CORE_EVERYDAY_TOOLS)
    fx = _names("dolar kaç TL")
    assert fx == {"fx_rate"}
    assert _select_tool_categories("dolar kaç TL") == {"web"}

def test_bugun_ne_oldu_haber_kategorisi() -> None:
    cats = _select_tool_categories("bugün ne oldu")
    assert cats is not None
    assert "web" in cats
    names = _names("bugün ne oldu")
    assert "web_news" in names
    assert names != set(CORE_EVERYDAY_TOOLS)

def test_kapat_belge_link_sozluk_tatil() -> None:
    assert "close_application" in _names("Notepad'i kapat")
    docs = _names("belgelerimde ara")
    assert "search_documents" in docs
    assert "search_documents" not in CORE_EVERYDAY_TOOLS
    link = _names("şu linki oku https://example.com")
    assert "web_fetch" in link
    assert "dict_lookup" in _names("merhaba kelime anlamı")
    assert "public_holidays" in _names("Türkiye resmi tatil listesi")
    assert "take_screenshot" in _names("ekran görüntüsü al")
    assert "get_battery_level" in _names("pil ne kadar")

def test_sunu_kaydet_filesystem() -> None:
    cats = _select_tool_categories("şunu kaydet")
    assert cats is not None
    assert "filesystem" in cats
    names = _names("şunu kaydet")
    assert "save_selected_text" in names
    assert "save_selected_text" not in CORE_EVERYDAY_TOOLS
    assert names != set(CORE_EVERYDAY_TOOLS)
    assert "save_selected_text" in _names("şunu not al")
    assert "save_selected_text" in _names("panodakini kaydet")

def test_masaustunu_listele() -> None:
    cats = _select_tool_categories("masaüstünü listele")
    assert cats is not None
    assert "filesystem" in cats
    names = _names("masaüstünü listele")
    assert "list_directory" in names
    assert "list_directory" not in CORE_EVERYDAY_TOOLS
    assert names != set(CORE_EVERYDAY_TOOLS)

def test_sesi_kis_set_volume() -> None:
    cats = _select_tool_categories("sesi kıs")
    assert cats is not None
    assert "system" in cats
    names = _names("sesi kıs")
    assert "set_volume" in names
    assert "set_volume" not in CORE_EVERYDAY_TOOLS
    assert names != set(CORE_EVERYDAY_TOOLS)

def test_hesap_ve_iban_enjekte() -> None:
    calc = _names("2+2 kaç eder")
    assert "calculate" in calc
    assert _select_tool_categories("2+2 kaç eder") is not None
    assert "system" in _select_tool_categories("hesapla 15*3")
    assert "calculate" in _names("hesapla 15*3")
    assert "calculate" in _names("100 km kaç mil")
    iban = _names("şu IBAN doğru mu")
    assert "iban_check" in iban
    assert "iban_check" in _names("IBAN doğrula")
    assert "iban_check" in CORE_EVERYDAY_TOOLS

def test_kopyala_pano_kilitle_cop() -> None:
    assert "copy_selected_text" in _names("şunu kopyala")
    assert "copy_selected_text" not in CORE_EVERYDAY_TOOLS
    assert "get_selected_text" in _names("şunu oku")
    assert "clipboard_read" in _names("panoda ne var")
    assert "clipboard_clear" in _names("panoyu temizle")
    assert "lock_workstation" in _names("bilgisayarı kilitle")
    assert "open_recycle_bin" in _names("geri dönüşüm kutusunu aç")
    assert "open_recycle_bin" not in CORE_EVERYDAY_TOOLS

def test_wifi_uptime_yazici_usb() -> None:
    assert "get_wifi_status" in _names("wifi durumu ne")
    assert "get_uptime" in _names("kaç saattir açık")
    assert "list_printers" in _names("yazıcıları listele")
    assert "list_removable_drives" in _names("USB sürücüler")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_ezan_deprem_posta() -> None:
    assert "prayer_times" in _names("Ankara ezan saatleri")
    assert "earthquakes" in _names("son depremler")
    assert "postal_lookup" in _names("34000 posta kodu neresi")
    assert "prayer_times" not in CORE_EVERYDAY_TOOLS
    assert "earthquakes" not in CORE_EVERYDAY_TOOLS

def test_pil_adlandir_git_pencere_cikar() -> None:
    assert "get_battery_level" in _names("pil yüzde kaç")
    assert "get_battery_level" not in CORE_EVERYDAY_TOOLS
    renamed = _names("masaüstünde rapor.pdf'i ozet.pdf olarak adlandır")
    assert "rename_file" in renamed
    assert "rename_file" not in CORE_EVERYDAY_TOOLS
    git = _names("masaüstünde Uryx_v2 git durumu")
    assert "git_status" in git
    assert "git" in (_select_tool_categories("masaüstünde Uryx_v2 git durumu") or set())
    assert "list_open_windows" in _names("açık pencereleri listele")
    assert "eject_removable_drive" in _names("E sürücüsünü çıkar")
    assert "eject_removable_drive" not in CORE_EVERYDAY_TOOLS
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_var_yol_satir_dil_tarayici_ayar() -> None:
    assert "file_exists" in _names("masaüstünde rapor.pdf var mı")
    assert "file_exists" not in CORE_EVERYDAY_TOOLS
    assert "copy_file_path" in _names("masaüstünde rapor.pdf yolunu kopyala")
    assert "count_file_lines" in _names("masaüstünde notlar.txt kaç satır")
    assert "get_system_locale" in _names("sistem dili nedir")
    assert "get_default_browser" in _names("varsayılan tarayıcı nedir")
    settings = _names("bluetooth ayarlarını aç")
    assert "open_windows_settings" in settings
    assert "open_windows_settings" not in CORE_EVERYDAY_TOOLS
    assert "application" in (_select_tool_categories("bluetooth ayarlarını aç") or set())
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_bosta_ekran_ip_disk_ad() -> None:
    assert "get_idle_time" in _names("kaç dakikadır boştayım göster")
    assert "get_display_info" in _names("ekran çözünürlüğü nedir")
    assert "get_network_interfaces" in _names("ip adresim nedir")
    assert "ip_lookup" not in _names("ip adresim nedir")
    assert "get_disk_usage" in _names("disk ne kadar dolu")
    assert "get_computer_info" in _names("bilgisayar adı nedir")
    assert "get_idle_time" not in CORE_EVERYDAY_TOOLS

def test_son_dosya_tasi_hash_cogalt_not() -> None:
    assert "list_recent_files" in _names("son indirilenler")
    assert "show_in_folder" in _names("indirilenlerde gezginde göster")
    assert "create_directory" in _names("masaüstünde arşiv klasörü oluştur")
    assert "get_file_info" in _names("masaüstünde rapor.pdf boyutu nedir")
    assert "move_file" in _names("masaüstündeki rapor.pdf'i belgelere taşı")
    assert "copy_file" in _names("masaüstündeki rapor.pdf'i belgelere kopyala")
    assert "get_file_hash" in _names("masaüstünde rapor.pdf sha256 nedir")
    assert "duplicate_file" in _names("masaüstünde rapor.pdf dosyasını çoğalt")
    assert "create_file" in _names("yeni not toplantı saat 10")
    assert "list_recent_files" not in CORE_EVERYDAY_TOOLS

def test_kurulu_calisiyor_on_plan_bildir() -> None:
    assert "list_installed_applications" in _names("chrome yüklü mü")
    assert "is_process_running" in _names("chrome çalışıyor mu")
    assert "list_processes" in _names("çalışan programlar")
    assert "get_foreground_window" in _names("hangi pencere açık")
    assert "notify_user" in _names("bana bildir toplantı var")
    assert "get_dark_mode" in _names("karanlık mod açık mı")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_saat_surucu_cop_yol_link_ulke() -> None:
    assert "get_system_time" in _names("saat kaç")
    assert "get_system_time" in _names("bugünün tarihi nedir")
    assert "get_system_time" not in CORE_EVERYDAY_TOOLS
    assert "prayer_times" in _names("İstanbul namaz saatleri")
    assert "get_system_time" not in _names("İstanbul namaz saatleri")
    assert "get_internet_status" in _names("internet var mı")
    assert "get_wifi_status" in _names("hangi ağa bağlıyım")
    assert "list_startup_apps" in _names("başlangıç programlarını listele")
    assert "list_logical_drives" in _names("sürücüleri listele")
    assert "get_recycle_bin_info" in _names("çöpte kaç öğe var")
    assert "get_special_folder_path" in _names("masaüstü yolu nedir")
    assert "get_folder_size" in _names("masaüstü ne kadar yer kaplıyor")
    assert "resolve_application_path" in _names("chrome nerede kurulu")
    assert "delete_file" in _names("masaüstünde rapor.pdf'i çöpe at")
    assert "search_files" in _names("fatura.pdf dosyasını ara")
    assert "get_power_status" in _names("pil durumu nedir")
    assert "get_selected_text" in _names("ne seçili")
    link = _names("şu linki aç https://example.com/x")
    assert "open_external_url" in link
    assert "web_fetch" not in link
    assert "browser_open" not in link
    chrome_link = _names("Chrome'da https://example.com aç")
    assert "web_search" in chrome_link
    assert "open_external_url" not in chrome_link
    assert "country_info" in _names("Türkiye'nin başkenti neresi")
    assert "sun_times" in _names("İstanbul gün batımı")
    assert "air_quality" in _names("İstanbul hava kalitesi")
    assert "get_cpu_usage" in _names("CPU kullanımı nedir")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_yazici_assoc_wifi_plan_profil_yeni() -> None:
    assert "get_default_printer" in _names("varsayılan yazıcı nedir")
    assert "get_default_printer" not in CORE_EVERYDAY_TOOLS
    assert "get_file_association" in _names("pdf hangi programla açılır")
    assert "list_nearby_wifi" in _names("yakındaki wifi ağları")
    assert "get_power_plan" in _names("güç planı nedir")
    assert "get_user_profile_path" in _names("kullanıcı klasörü nedir")
    assert "get_special_folder_path" in _names("masaüstü yolu nedir")
    assert "list_files_by_extension" in _names("masaüstündeki pdf'leri listele")
    assert "get_newest_file" in _names("en son indirilen dosya")
    assert "is_directory_empty" in _names("masaüstü boş mu")
    assert "clipboard_write" in _names("panoya yaz merhaba dünya")
    assert "get_ram_usage" in _names("RAM kullanımı nedir")
    assert "get_gpu_usage" in _names("GPU kullanımı nedir")
    assert "list_installed_applications" in _names("kurulu uygulamalar")
    assert "get_uptime" in _names("bilgisayar ne zamandır açık")
    assert "get_display_info" in _names("kaç monitör var")
    assert "get_wifi_status" in _names("wifi adı nedir")
    assert "get_file_association" in _names("pdf'i hangi program açar")
    assert "get_user_profile_path" in _names("kullanıcı klasörüm nerede")
    assert "list_nearby_wifi" in _names("yakındaki wifi ağlarını listele")
    assert "get_newest_file" in _names("en son indirilen dosya nedir")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_en_buyuk_kac_pdf_boot_model_gece() -> None:
    assert "get_largest_file" in _names("masaüstünde en büyük dosya")
    assert "get_largest_file" not in CORE_EVERYDAY_TOOLS
    assert "count_files_by_extension" in _names("masaüstünde kaç pdf var")
    assert "list_directory" in _names("masaüstünde kaç dosya var")
    assert "list_files_by_extension" in _names("masaüstündeki pdf'leri listele")
    assert "list_subdirectories" in _names("masaüstündeki klasörleri listele")
    assert "list_today_files" in _names("bugün indirilenler")
    assert "list_recent_files" in _names("son indirilenler")
    assert "get_last_boot_time" in _names("son açılış ne zaman")
    assert "get_uptime" in _names("bilgisayar ne zamandır açık")
    assert "get_system_model" in _names("bilgisayar modeli nedir")
    assert "get_computer_info" in _names("bilgisayar adı nedir")
    assert "get_night_light" in _names("gece ışığı açık mı")
    assert "get_dark_mode" in _names("karanlık mod açık mı")
    assert "get_bluetooth_status" in _names("bluetooth açık mı")
    assert "open_windows_settings" in _names("bluetooth ayarlarını aç")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_eski_klasor_dilim_radyo_hoparlor() -> None:
    assert "get_oldest_file" in _names("masaüstünde en eski dosya")
    assert "get_oldest_file" not in CORE_EVERYDAY_TOOLS
    assert "get_largest_file" in _names("masaüstünde en büyük dosya")
    assert "count_subdirectories" in _names("masaüstünde kaç klasör var")
    assert "list_subdirectories" in _names("masaüstündeki klasörleri listele")
    assert "list_directory" in _names("masaüstünde kaç dosya var")
    assert "get_timezone" in _names("saat dilimi nedir")
    assert "get_system_time" in _names("saat kaç")
    assert "get_temp_folder_path" in _names("geçici klasör nerede")
    assert "get_user_profile_path" in _names("kullanıcı klasörüm nerede")
    assert "get_wallpaper_path" in _names("duvar kağıdı nedir")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert "get_wifi_status" in _names("hangi ağa bağlıyım")
    assert "get_default_playback_device" in _names("hangi hoparlör")
    assert "get_volume" in _names("ses kaç")
    assert "get_drive_label" in _names("C sürücüsünün adı nedir")
    assert "list_logical_drives" in _names("sürücüleri listele")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_ekle_medya_tara_docker_duzenle() -> None:
    assert "save_selected_text" in _names("şunu notlar.txt'ye ekle")
    assert "save_selected_text" in _names("şunu masaüstüne at")
    assert "set_volume" in _names("sesi yüzde 30 yap")
    assert "control_media_playback" in _names("sonraki şarkı")
    assert "control_media_playback" in _names("müziği duraklat")
    assert "control_media_playback" not in CORE_EVERYDAY_TOOLS
    assert "inspect_application" in _names("notepad arayüzünü tara")
    assert "open_vscode" in _names("vscode aç")
    assert "get_docker_engine_status" in _names("docker çalışıyor mu")
    assert "edit_file" in _names("masaüstünde notlar.txt düzenle")
    assert "read_file" in _names("masaüstünde notlar.txt oku")
    assert "list_directory" in _names("masaüstünde kaç dosya var")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_iss_polen_doi_spotify_kripto() -> None:
    assert "iss_now" in _names("ISS nerede")
    assert "iss_now" not in CORE_EVERYDAY_TOOLS
    assert "space_weather" in _names("uzay havası aurora")
    assert "weather" not in _names("uzay havası aurora")
    assert "doi_lookup" in _names("şu DOI 10.1038/nphys1170")
    assert "elevation" in _names("Everest rakımı nedir")
    assert "pypi_lookup" in _names("httpx pypi paket sürümü")
    assert "npm_lookup" in _names("react npm paket sürümü")
    assert "dns_lookup" in _names("example.com dns kaydı")
    assert "pollen" in _names("İstanbul polen durumu")
    assert "air_quality" not in _names("İstanbul polen durumu")
    assert "food_barcode" in _names("3017620422003 barkod nedir")
    public_ip = _names("8.8.8.8 nerede")
    assert "ip_lookup" in public_ip
    assert "get_network_interfaces" not in public_ip
    assert "ip_lookup" not in _names("ip adresim nedir")
    btc = _names("bitcoin kaç dolar")
    assert "web_search" in btc
    assert "fx_rate" not in btc
    assert "weather" in _names("İstanbul'da hava nasıl")
    assert "public_holidays" in _names("bu yıl resmi tatiller neler")
    assert "dict_lookup" in _names("merhaba ne demek")
    assert "open_application" in _names("Spotify'ı aç")
    assert "open_application" in _names("ayarlar aç")
    assert "get_selected_text" in _names("şunu yap")
    assert "save_selected_text" in _names("şunu belgelere kaydet notlar.txt")
    assert "take_screenshot" in _names("ekran görüntüsünü kaydet")
    assert "list_removable_drives" in _names("takılı usb var mı göster")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_git_docker_sessiz_resim_onceki() -> None:
    assert "git_commit" in _names("git commit")
    assert "git_push" in _names("git push")
    assert "git_status" in _names("masaüstünde Uryx_v2 git durumu")
    assert "git_commit" not in CORE_EVERYDAY_TOOLS
    assert "docker_list_containers" in _names("konteynerleri listele")
    assert "open_docker_desktop" in _names("docker desktop aç")
    assert "get_docker_desktop_logs" in _names("docker logları")
    assert "set_volume" in _names("sessiz yap")
    assert "open_folder" in _names("resimleri aç")
    assert "control_media_playback" in _names("önceki şarkı")
    assert "control_media_playback" in _names("müziği devam ettir")
    assert "get_night_light" in _names("mavi ışık açık mı")
    assert "get_system_model" in _names("cihaz modeli nedir")
    assert "list_subdirectories" in _names("masaüstündeki klasörler")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_en_eski_kac_klasor_dilim_temp() -> None:
    oldest = _names("masaüstünde en eski dosya")
    assert "get_oldest_file" in oldest
    assert "get_oldest_file" not in CORE_EVERYDAY_TOOLS
    assert "get_newest_file" in _names("en son indirilen dosya nedir")
    assert "get_largest_file" in _names("masaüstünde en büyük dosya")
    assert "count_subdirectories" in _names("masaüstünde kaç klasör var")
    assert "count_subdirectories" in _names("masaüstünde kaç tane klasör")
    assert "list_subdirectories" in _names("masaüstündeki klasörleri listele")
    assert "list_directory" in _names("masaüstünde kaç dosya var")
    assert "get_timezone" in _names("saat dilimi nedir")
    assert "get_system_time" in _names("saat kaç")
    assert "get_temp_folder_path" in _names("geçici klasör yolu nedir")
    assert "get_temp_folder_path" in _names("temp klasör nerede")
    assert "get_user_profile_path" in _names("kullanıcı klasörüm nerede")
    assert "get_wallpaper_path" in _names("duvar kağıdı yolu nedir")
    assert "take_screenshot" in _names("ekran görüntüsünü kaydet")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert "get_wifi_status" in _names("wifi adı nedir")
    assert "list_nearby_wifi" in _names("yakındaki wifi ağlarını listele")
    assert "get_default_playback_device" in _names("varsayılan hoparlör nedir")
    assert "get_volume" in _names("ses kaç")
    assert "get_drive_label" in _names("C sürücüsünün adı")
    assert "get_drive_label" in _names("C sürücü etiketi")
    assert "list_logical_drives" in _names("sürücüleri listele")
    assert "get_disk_usage" in _names("disk ne kadar dolu")
    assert "get_wallpaper_path" in _names("duvar kâğıdı nerede")
    assert "get_network_interfaces" in _names("ağ arayüzlerim")
    assert "get_wifi_radio" in _names("wifi kapalı mı")
    assert "get_default_playback_device" in _names("hangi hoparlör")
    assert "set_volume" in _names("sessiz ol")
    assert "docker_stop_container" in _names("konteyneri durdur")
    assert "control_media_playback" in _names("şarkıyı duraklat")
    assert "get_timezone" in _names("saat dilimim ne")
    assert "get_oldest_file" in _names("en eski indirilen dosya")
    assert "count_subdirectories" in _names("belgelerimde kaç klasör var")
    assert "get_wifi_radio" in _names("wifi radyo açık mı")
    assert "get_default_playback_device" in _names("ses çıkış aygıtı nedir")
    assert "get_drive_label" in _names("D sürücüsünün adı")
    assert "get_timezone" in _names("timezone nedir")
    assert "get_wallpaper_path" in _names("wallpaper yolu")
    assert "list_startup_apps" in _names("başlangıç programları")
    assert "get_foreground_window" in _names("ön plandaki pencere")
    assert "count_files_by_extension" in _names("masaüstünde kaç jpeg var")
    assert "open_recycle_bin" in _names("recycle bin aç")
    assert "set_volume" in _names("sesi mute et")
    assert "get_network_interfaces" in _names("ethernet IP nedir")
    assert "get_network_interfaces" in _names("LAN adreslerim")
    assert "get_gpu_usage" in _names("ekran kartı kullanımı")
    assert "get_recycle_bin_info" in _names("çöp bilgisi")
    assert "get_power_status" in _names("güç durumu nedir")
    assert "get_power_plan" in _names("güç planı nedir")
    assert "get_idle_time" in _names("boşta ne kadar")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_kucuk_hafta_onedrive_cpu_mic() -> None:
    assert "get_smallest_file" in _names("masaüstünde en küçük dosya")
    assert "get_smallest_file" not in CORE_EVERYDAY_TOOLS
    assert "get_largest_file" in _names("masaüstünde en büyük dosya")
    assert "get_oldest_file" in _names("masaüstünde en eski dosya")
    assert "list_this_week_files" in _names("bu hafta indirilenler")
    assert "list_today_files" in _names("bugün indirilenler")
    assert "list_recent_files" in _names("son indirilenler")
    assert "get_onedrive_path" in _names("onedrive klasör yolu")
    assert "get_user_profile_path" in _names("kullanıcı klasörüm nerede")
    assert "get_temp_folder_path" in _names("geçici klasör yolu nedir")
    assert "get_cpu_name" in _names("işlemci adı nedir")
    assert "get_cpu_usage" in _names("işlemci kullanımı nedir")
    assert "get_gpu_name" in _names("ekran kartı adı nedir")
    assert "get_gpu_usage" in _names("ekran kartı kullanımı")
    assert "get_ethernet_status" in _names("ethernet bağlı mı")
    assert "get_wifi_status" in _names("wifi adı nedir")
    assert "get_network_interfaces" in _names("ip adresim nedir")
    assert "get_default_recording_device" in _names("hangi mikrofon")
    assert "get_default_playback_device" in _names("hangi hoparlör")
    assert "get_refresh_rate" in _names("yenileme hızı nedir")
    assert "get_refresh_rate" in _names("kaç hertz")
    assert "get_display_info" in _names("kaç monitör var")
    assert "get_smallest_file" in _names("en küçük indirilen dosya")
    assert "get_default_recording_device" in _names("varsayılan mikrofon")
    assert "get_ethernet_status" in _names("kablolu ağ bağlı mı")
    assert "get_cpu_name" in _names("cpu model nedir")
    assert "get_onedrive_path" in _names("onedrive nerede")
    assert "get_gpu_name" in _names("hangi ekran kartı")
    assert "get_gpu_name" in _names("ekran kartım ne")
    assert "get_ethernet_status" in _names("kablolu internet bağlı mı")
    assert "get_refresh_rate" in _names("ekran yenileme")
    assert "get_smallest_file" in _names("en ufak dosya")
    assert "list_this_week_files" in _names("bu haftaki dosyalar")
    assert "get_cpu_name" in _names("hangi işlemci")
    assert "get_ethernet_status" in _names("lan bağlı mı")
    assert "get_refresh_rate" in _names("kaç hz")
    assert "get_onedrive_path" in _names("one drive nerede")
    assert "get_default_recording_device" in _names("mikrofon hangisi")
    assert "get_refresh_rate" in _names("ekran kaç hz")
    assert "list_this_week_files" in _names("bu hafta değişenler")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_temp_sarj_tarayici_kablolu() -> None:
    assert "get_temp_folder_path" in _names("temp nerede")
    assert "get_temp_folder_path" in _names("geçici dosyalar nerede")
    assert "get_temp_folder_path" not in CORE_EVERYDAY_TOOLS
    assert "get_default_recording_device" in _names("kayıt cihazı nedir")
    assert "get_network_interfaces" in _names("IPv6 adresim")
    assert "get_network_interfaces" in _names("yerel IP'lerim")
    assert "get_network_interfaces" in _names("ağ kartlarım")
    assert "get_battery_level" in _names("şarjım kaç")
    assert "get_dark_mode" in _names("karanlık tema açık mı")
    assert "get_dark_mode" in _names("gece modu açık mı")
    assert "get_night_light" in _names("gece ışığı açık mı")
    assert "list_startup_apps" in _names("başlangıçta açılanlar")
    assert "get_default_browser" in _names("hangi tarayıcı")
    assert "get_ethernet_status" in _names("kablolu bağlı mı")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_dun_olcek_ram_cekirdek_ucak() -> None:
    assert "list_yesterday_files" in _names("dün indirilenler")
    assert "list_yesterday_files" not in CORE_EVERYDAY_TOOLS
    assert "list_today_files" in _names("bugün indirilenler")
    assert "list_this_week_files" in _names("bu hafta indirilenler")
    assert "count_today_files" in _names("bugün kaç dosya indirildi")
    assert "list_directory" in _names("masaüstünde kaç dosya var")
    assert "get_screen_scale" in _names("ekran ölçeği nedir")
    assert "get_refresh_rate" in _names("yenileme hızı nedir")
    assert "get_display_info" in _names("kaç monitör var")
    assert "get_ram_size" in _names("kaç GB ram")
    assert "get_ram_usage" in _names("RAM kullanımı nedir")
    assert "get_cpu_count" in _names("kaç çekirdek")
    assert "get_cpu_name" in _names("işlemci adı nedir")
    assert "get_cpu_usage" in _names("işlemci kullanımı nedir")
    assert "get_mute_status" in _names("ses kapalı mı")
    assert "set_volume" in _names("sessiz yap")
    assert "get_volume" in _names("ses kaç")
    assert "get_drive_filesystem" in _names("C dosya sistemi nedir")
    assert "get_drive_label" in _names("C sürücüsünün adı")
    assert "get_disk_usage" in _names("disk ne kadar dolu")
    assert "get_airplane_mode" in _names("uçak modu açık mı")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert "list_yesterday_files" in _names("dün değişen dosyalar")
    assert "get_screen_scale" in _names("ekran dpi")
    assert "get_ram_size" in _names("toplam bellek")
    assert "get_cpu_count" in _names("çekirdek sayısı")
    assert "get_mute_status" in _names("sessiz mi")
    assert "get_drive_filesystem" in _names("C NTFS mi")
    assert "list_yesterday_files" in _names("dün indirdiklerim")
    assert "count_today_files" in _names("bugün kaç tane indi")
    assert "get_screen_scale" in _names("ekran yüzde kaç")
    assert "get_screen_scale" in _names("ekran scale")
    assert "get_cpu_count" in _names("kaç tane çekirdek")
    assert "get_cpu_count" in _names("çekirdek kaç tane")
    assert "get_drive_filesystem" in _names("C formatı nedir")
    assert "get_mute_status" in _names("ses açık mı")
    assert "list_yesterday_files" in _names("yesterday downloads")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_ay_vpn_parlaklik_klavye() -> None:
    assert "list_this_month_files" in _names("bu ay indirilenler")
    assert "list_this_month_files" not in CORE_EVERYDAY_TOOLS
    assert "list_this_week_files" in _names("bu hafta indirilenler")
    assert "list_yesterday_files" in _names("dün indirilenler")
    assert "count_yesterday_files" in _names("dün kaç dosya indirildi")
    assert "count_today_files" in _names("bugün kaç dosya indirildi")
    assert "get_os_version" in _names("windows sürümü nedir")
    assert "get_computer_info" in _names("bilgisayar adı nedir")
    assert "get_username" in _names("kullanıcı adım ne")
    assert "get_user_profile_path" in _names("kullanıcı klasörüm nerede")
    assert "get_brightness" in _names("parlaklık kaç")
    assert "get_screen_scale" in _names("ekran ölçeği nedir")
    assert "get_night_light" in _names("gece ışığı açık mı")
    assert "get_vpn_status" in _names("vpn bağlı mı")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert "get_keyboard_layout" in _names("klavye dili nedir")
    assert "get_system_locale" in _names("sistem dili nedir")
    assert "get_battery_saver" in _names("pil tasarrufu açık mı")
    assert "get_battery_level" in _names("pil yüzde kaç")
    assert "list_this_month_files" in _names("bu ayki dosyalar")
    assert "count_yesterday_files" in _names("dün kaç tane indi")
    assert "get_os_version" in _names("hangi windows")
    assert "get_os_version" in _names("işletim sistemi sürümü")
    assert "get_username" in _names("hangi kullanıcı")
    assert "get_brightness" in _names("ekran parlaklığı")
    assert "get_vpn_status" in _names("sanal özel ağ")
    assert "get_keyboard_layout" in _names("klavye düzeni")
    assert "get_battery_saver" in _names("enerji tasarrufu")
    assert "list_this_month_files" in _names("this month files")
    assert "list_this_month_files" in _names("bu ayki indirmeler")
    assert "count_yesterday_files" in _names("dün kaç indi")
    assert "get_os_version" in _names("windows version")
    assert "get_os_version" in _names("hangi sürüm windows")
    assert "get_username" in _names("oturum kullanıcısı")
    assert "get_username" in _names("hesap adım")
    assert "get_brightness" in _names("ekran ışığı kaç")
    assert "get_brightness" in _names("ekran ne kadar parlak")
    assert "get_keyboard_layout" in _names("hangi klavye")
    assert "get_keyboard_layout" in _names("klavye türkçe mi")
    assert "get_battery_saver" in _names("tasarruf modu açık mı")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_hafta_sinyal_guvenlik_posta() -> None:
    assert "count_this_week_files" in _names("bu hafta kaç dosya indirildi")
    assert "count_this_week_files" not in CORE_EVERYDAY_TOOLS
    assert "list_this_week_files" in _names("bu hafta indirilenler")
    assert "count_this_month_files" in _names("bu ay kaç dosya indirildi")
    assert "list_this_month_files" in _names("bu ay indirilenler")
    assert "get_architecture" in _names("64 bit mi")
    assert "get_os_version" in _names("windows sürümü nedir")
    assert "get_focus_assist" in _names("odaklanma yardımı açık mı")
    assert "get_mute_status" in _names("ses kapalı mı")
    assert "get_firewall_status" in _names("güvenlik duvarı açık mı")
    assert "get_default_mail_app" in _names("hangi e-posta uygulaması")
    assert "get_default_browser" in _names("varsayılan tarayıcı nedir")
    assert "get_screenshots_folder" in _names("ekran görüntüleri klasörü nerede")
    assert "take_screenshot" in _names("ekran görüntüsü al")
    assert "get_wifi_signal" in _names("wifi sinyal kaç")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_ssid_tarih_pushla_idle() -> None:
    assert "list_yesterday_files" in _names("dün ne indirdim")
    assert "get_ram_size" in _names("belleğim ne kadar")
    assert "get_cpu_count" in _names("kaç logical processor")
    assert "get_airplane_mode" in _names("airplane açık mı")
    assert "get_idle_time" in _names("boşta kaç dk")
    assert "get_idle_time" in _names("idle time")
    assert "get_file_association" in _names("hangi pdf açar")
    assert "get_user_profile_path" in _names("home directory")
    assert "get_disk_usage" in _names("C dolu mu")
    assert "get_internet_status" in _names("internetim var mı")
    assert "get_internet_status" in _names("net kesik mi")
    assert "get_wifi_status" in _names("ssid nedir")
    assert "get_dark_mode" in _names("koyu mod")
    assert "get_system_time" in _names("tarih kaç")
    assert "get_system_locale" in _names("dil ayarı nedir")
    assert "get_default_browser" in _names("varsayılan browser")
    assert "get_power_plan" in _names("güç şeması")
    assert "get_power_status" in _names("prize takılı mı")
    assert "list_open_windows" in _names("açık uygulamalar")
    assert "git_push" in _names("pushla")
    assert "list_processes" in _names("görev listesi")
    assert "list_calendar_events" in _names("takvimim")
    assert "list_calendar_events" in _names("randevularım")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)
    assert "get_cpu_count" in _names("çekirdeğim kaç")
    assert "get_drive_filesystem" in _names("C FAT mı")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_dunkü_exfat_netim_kilit() -> None:
    assert "list_yesterday_files" in _names("dünkü indirmeler")
    assert "list_yesterday_files" in _names("dünkü değişiklikler")
    assert "get_screen_scale" in _names("ekran büyütme yüzde")
    assert "get_screen_scale" in _names("ekran zoom yüzde")
    assert "get_drive_filesystem" in _names("C exFAT mi")
    assert "get_mute_status" in _names("sessizlik durumu")
    assert "get_airplane_mode" in _names("flight mode açık mı")
    assert "get_internet_status" in _names("netim var mı")
    assert "get_system_time" in _names("tarihim ne")
    assert "get_power_status" in _names("şarj kablosu takılı mı")
    assert "list_processes" in _names("görevler listesi")
    assert "lock_workstation" in _names("ekran kilidi")
    assert "open_vscode" in _names("code aç")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)

def test_hafta_mimari_firewall_mail() -> None:
    assert "count_this_week_files" in _names("bu hafta kaç dosya indirildi")
    assert "count_this_week_files" not in CORE_EVERYDAY_TOOLS
    assert "list_this_week_files" in _names("bu hafta indirilenler")
    assert "count_this_month_files" in _names("bu ay kaç dosya indirildi")
    assert "list_this_month_files" in _names("bu ay indirilenler")
    assert "count_yesterday_files" in _names("dün kaç dosya indirildi")
    assert "get_architecture" in _names("sistem mimarisi nedir")
    assert "get_os_version" in _names("windows sürümü nedir")
    assert "get_cpu_name" in _names("işlemci adı nedir")
    assert "get_focus_assist" in _names("odaklanma açık mı")
    assert "get_mute_status" in _names("ses kapalı mı")
    assert "get_night_light" in _names("gece ışığı açık mı")
    assert "get_firewall_status" in _names("güvenlik duvarı açık mı")
    assert "get_default_mail_app" in _names("varsayılan e-posta nedir")
    assert "get_default_browser" in _names("hangi tarayıcı")
    assert "get_screenshots_folder" in _names("ekran görüntüleri klasörü")
    assert "take_screenshot" in _names("ekran görüntüsü al")
    assert "get_wifi_signal" in _names("wifi sinyali kaç")
    assert "get_wifi_status" in _names("ssid nedir")
    assert "get_wifi_radio" in _names("wifi açık mı")
    assert "count_this_week_files" in _names("bu hafta kaç tane indi")
    assert "get_architecture" in _names("64 bit miyim")
    assert "get_focus_assist" in _names("rahatsız etme açık mı")
    assert "get_default_mail_app" in _names("hangi e-posta uygulaması")
    assert "get_screenshots_folder" in _names("screenshots folder")
    assert "count_this_week_files" in _names("bu haftaki sayı")
    assert "count_this_week_files" in _names("hafta kaç tane indi")
    assert "count_this_month_files" in _names("bu ayki sayı")
    assert "count_this_month_files" in _names("ay kaç tane indi")
    assert "get_architecture" in _names("kaç bitim")
    assert "get_focus_assist" in _names("do not disturb")
    assert "get_focus_assist" in _names("bildirimleri kapalı mı")
    assert "get_default_mail_app" in _names("hangi mail")
    assert "get_screenshots_folder" in _names("ekran görüntüleri nerede")
    assert "get_wifi_signal" in _names("wifi çekim")
    assert "get_wifi_signal" in _names("rssi kaç")
    assert "count_this_week_files" in _names("haftalık indirme sayısı")
    assert "count_this_month_files" in _names("aylık indirme sayısı")
    assert "count_this_month_files" in _names("this month how many")
    assert "get_focus_assist" in _names("odak yardımı açık mı")
    assert "get_focus_assist" in _names("bildirim kapalı mı")
    assert "get_default_mail_app" in _names("varsayılan posta")
    assert "get_wifi_signal" in _names("sinyal gücü nedir")
    assert _names("yarın ne yapmalıyım") == set(CORE_EVERYDAY_TOOLS)
