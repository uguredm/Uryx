"""Araç kayıt defteri (allowlist).

Modele **yalnızca** burada tanımlı araçlar sunulur. Serbest shell erişimi
verilmez; ``run_powershell`` gibi araçlar bile sabit bir tanım, JSON-Schema
doğrulaması ve zorunlu kullanıcı onayı arkasındadır.

``execution`` alanı aracın nerede çalıştığını belirler:

* ``HOST``    → Electron main process (Windows tarafı)
* ``BACKEND`` → uryx-api container'ı
"""

from __future__ import annotations

import json
from typing import Any

from app.core.errors import ToolNotAllowedError, ValidationError
from app.core.locale import loc, localize_tool
from app.schemas.tools import (
    ExecutionTarget,
    RiskLevel,
    ToolDefinition,
    ToolParameter,
)

HOST = ExecutionTarget.HOST
BACKEND = ExecutionTarget.BACKEND
LOW = RiskLevel.LOW
MEDIUM = RiskLevel.MEDIUM
HIGH = RiskLevel.HIGH

def _p(
    name: str,
    description: str,
    *,
    type_: str = "string",
    required: bool = False,
    enum: list[str] | None = None,
    default: Any | None = None,
) -> ToolParameter:
    """Kısa parametre yardımcısı."""
    return ToolParameter(
        name=name,
        type=type_,
        description=description,
        required=required,
        enum=enum,
        default=default,
    )

TOOL_DEFINITIONS: list[ToolDefinition] = [

    ToolDefinition(
        name="open_application",
        display_name="Program aç",
        description=(
            "Windows'ta bir programı açar. Kullanıcının söylediği görünen uygulama adını Windows "
            "Başlat menüsündeki kurulu uygulamalarla güvenli biçimde eşleştirir; yeni kurulan "
            "uygulamalar ayrıca izin listesi güncellemesi gerektirmez. Bilinen takma adlar "
            "(notepad, calc, explorer, chrome, edge, vscode, terminal, spotify, task_manager, "
            "settings, cmd, powershell) ve izin verilen bir klasördeki .exe/.lnk yolu da "
            "kabul edilir."
        ),
        category="application",
        risk=MEDIUM,
        execution=HOST,
        impact="Bilgisayarınızda yeni bir program penceresi açılır.",
        parameters=[
            _p(
                "name",
                "Uygulamanın görünen adı, takma adı veya izin verilen tam yolu",
                required=True,
            ),
            _p("args", "Programa geçirilecek argümanlar (tek metin)"),
        ],
    ),
    ToolDefinition(
        name="close_application",
        display_name="Program kapat",
        description="Adı verilen programı nazikçe kapatır (pencere kapatma sinyali gönderir).",
        category="application",
        risk=MEDIUM,
        execution=HOST,
        impact="Açık program kapanır; kaydedilmemiş veriler kaybolabilir.",
        parameters=[_p("name", "Program adı (ör. notepad)", required=True)],
    ),
    ToolDefinition(
        name="open_media_application",
        display_name="Yerel medya uygulamasında aç",
        description=(
            "Bir şarkı veya videoyu önce bilgisayarda kurulu desteklenen medya uygulamasında "
            "arar/açar. Kullanıcı özellikle Spotify gibi kurulu bir uygulamada açmayı ya da "
            "çalmayı istediğinde kullan. Uygulama kurulu değilse sonuç hata döner ve web yedeği "
            "kullanılabilir."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        impact="Kurulu medya uygulaması açılır ve istenen içerik aranır.",
        parameters=[
            _p("app", "Medya uygulaması", required=True, enum=["spotify"]),
            _p("query", "Uygulama içinde aranacak sanatçı, şarkı veya içerik", required=True),
            _p("url", "Doğrulanmış web sonucunun adresi"),
            _p(
                "kind",
                "Spotify hedef türü: liked (beğenilenler), track, album, artist, playlist, search",
            ),
            _p(
                "autoplay",
                "Doğrulanmış içerik açıldıktan sonra oynatmayı başlat ve durumunu doğrula",
                type_="boolean",
                default=True,
            ),
        ],
    ),
    ToolDefinition(
        name="control_media_playback",
        display_name="Medya oynatmayı kontrol et",
        description=(
            "Spotify'daki mevcut oynatmayı UI Automation üzerinden oynatır, duraklatır, "
            "sonraki/önceki parçaya geçirir veya uygulamayı kapatır; sonucu gözlemleyerek "
            "doğrular. Kullanıcı müziği durdur, devam ettir, sonraki şarkı veya Spotify'ı "
            "kapat dediğinde kullan."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        impact="Spotify oynatma durumu değiştirilir veya Spotify kapatılır.",
        parameters=[
            _p("app", "Medya uygulaması", required=True, enum=["spotify"]),
            _p(
                "action",
                "Uygulanacak oynatma komutu",
                required=True,
                enum=["play", "pause", "next", "previous", "close"],
            ),
        ],
    ),
    ToolDefinition(
        name="list_installed_applications",
        display_name="Kurulu uygulamaları listele",
        description=(
            "Windows Başlat menüsündeki kurulu uygulamaların güvenilir görünen adlarını listeler. "
            "Bir uygulamanın kurulu olup olmadığını veya hangi adla açılacağını öğrenmek için "
            "kullan."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        impact="Yalnızca yerel kurulu uygulama adları okunur.",
        parameters=[_p("query", "İsteğe bağlı uygulama adı filtresi")],
    ),
    ToolDefinition(
        name="inspect_application",
        display_name="Uygulama arayüzünü tara",
        description=(
            "Açık bir Windows uygulamasının UI Automation erişilebilirlik ağacını salt okunur "
            "olarak tarar; pencere, düğme, metin alanı, liste ve diğer kontrolleri döndürür. "
            "Kullanıcı kendi uygulamasını incelemeyi/taramayı istediğinde önce bunu kullan."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        impact="Seçilen açık uygulamanın ekranda görünen erişilebilir kontrol bilgileri okunur.",
        parameters=[
            _p("name", "Açık uygulamanın veya pencerenin görünen adı", required=True),
            _p("limit", "En fazla kontrol sayısı", type_="integer", default=160),
        ],
    ),
    ToolDefinition(
        name="open_vscode",
        display_name="VS Code aç",
        description="Visual Studio Code'u açar; klasör yolu verilirse o klasörü açar.",
        category="application",
        risk=MEDIUM,
        execution=HOST,
        impact="VS Code penceresi açılır.",
        parameters=[_p("path", "Açılacak klasör veya dosya yolu (isteğe bağlı)")],
    ),
    ToolDefinition(
        name="open_folder",
        display_name="Klasör aç",
        description=(
            "Windows Gezgini'nde bir klasörü açar. Masaüstü/Belgeler/İndirilenler/Resimler "
            "için path olarak desktop, documents, downloads veya pictures yaz."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Dosya gezgini penceresi açılır.",
        parameters=[_p("path", "Klasör yolu veya desktop/documents/downloads/pictures", required=True)],
    ),
    ToolDefinition(
        name="open_recycle_bin",
        display_name="Geri Dönüşüm Kutusu",
        description=(
            "Windows Geri Dönüşüm Kutusu'nu Gezgin'de açar. "
            "Kullanıcı 'geri dönüşüm / çöp kutusunu aç' dediğinde kullan. İçini boşaltmaz."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Geri Dönüşüm Kutusu penceresi açılır; dosya silinmez.",
        parameters=[],
    ),
    ToolDefinition(
        name="get_recycle_bin_info",
        display_name="Geri Dönüşüm bilgisi",
        description=(
            "Geri Dönüşüm Kutusu'ndaki öğe sayısını ve boyutu okur. "
            "Boşaltmaz. Kullanıcı 'çöpte kaç öğe' dediğinde kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="open_windows_settings",
        display_name="Windows Ayarları sayfası",
        description=(
            "İzinli bir ms-settings sayfasını açar (bluetooth/wifi/display/sound/"
            "update/about/datetime/apps). Serbest kabuk yok. "
            "Kullanıcı 'bluetooth ayarlarını aç' dediğinde kullan. "
            "Çıplak 'ayarları aç' için open_application kullan."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        impact="Windows Ayarları'nda izinli bir sayfa açılır.",
        parameters=[
            _p(
                "page",
                "Ayarlar sayfası",
                required=True,
                enum=[
                    "bluetooth",
                    "wifi",
                    "display",
                    "sound",
                    "update",
                    "about",
                    "datetime",
                    "apps",
                ],
            ),
        ],
    ),
    ToolDefinition(
        name="resolve_application_path",
        display_name="Uygulama yolu",
        description=(
            "Allowlist uygulamasının kurulum/komut yolunu okur. Açmaz. "
            "Kullanıcı 'chrome nerede kurulu' dediğinde kullan. "
            "yüklü mü için list_installed_applications kullan."
        ),
        category="application",
        risk=LOW,
        execution=HOST,
        parameters=[_p("name", "Uygulama takma adı", required=True)],
    ),
    ToolDefinition(
        name="list_directory",
        display_name="Klasör içeriğini listele",
        description=(
            "İzin verilen bir klasördeki dosya ve alt klasörleri listeler. "
            "Kullanıcı 'klasördekileri göster/listele' dediğinde kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", required=True),
            _p("limit", "En fazla kayıt", type_="integer", default=80),
        ],
    ),
    ToolDefinition(
        name="copy_file",
        display_name="Dosya kopyala",
        description="İzin verilen klasörler içinde bir dosyayı yeni yola kopyalar. Var olanın üzerine yazmaz.",
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Diskte yeni bir dosya kopyası oluşur.",
        parameters=[
            _p("source", "Kaynak dosya yolu", required=True),
            _p("destination", "Hedef dosya yolu", required=True),
        ],
    ),
    ToolDefinition(
        name="move_file",
        display_name="Dosya taşı",
        description=(
            "İzin verilen klasörler içinde bir dosyayı yeni yola taşır. "
            "Var olanın üzerine yazmaz. Kullanıcı 'taşı / taşıyıver' dediğinde kullan."
        ),
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Dosya konumu değişir; üzerine yazılmaz.",
        parameters=[
            _p("source", "Kaynak dosya yolu", required=True),
            _p("destination", "Hedef dosya yolu", required=True),
        ],
    ),
    ToolDefinition(
        name="rename_file",
        display_name="Dosyayı yeniden adlandır",
        description=(
            "İzinli kökte bir dosyayı aynı klasörde yeni adla adlandırır. "
            "Üzerine yazmaz. Kullanıcı 'X'i Y olarak adlandır' dediğinde kullan."
        ),
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Dosya adı değişir; üzerine yazılmaz.",
        parameters=[
            _p("source", "Kaynak dosya yolu", required=True),
            _p("name", "Yeni dosya adı (yol yok)", required=True),
        ],
    ),
    ToolDefinition(
        name="duplicate_file",
        display_name="Dosyayı çoğalt",
        description=(
            "İzinli bir dosyanın aynı klasörde -kopya kopyasını oluşturur. "
            "Üzerine yazmaz. Kullanıcı 'çoğalt / kopyasını çıkar' dediğinde kullan."
        ),
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Diskte yeni bir kopya oluşur.",
        parameters=[_p("path", "Kaynak dosya yolu", required=True)],
    ),
    ToolDefinition(
        name="get_file_hash",
        display_name="Dosya özeti (SHA-256)",
        description="İzinli bir dosyanın SHA-256 özetini okur. İçeriği döndürmez.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Dosya yolu", required=True)],
    ),
    ToolDefinition(
        name="file_exists",
        display_name="Dosya var mı",
        description="İzinli kökte dosya veya klasörün varlığını kontrol eder. İçerik okumaz.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Dosya veya klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="copy_file_path",
        display_name="Dosya yolunu kopyala",
        description=(
            "İzinli bir dosyanın tam yolunu panoya yazar. Dosyayı kopyalamaz. "
            "Kullanıcı 'yolunu kopyala' dediğinde kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Pano içeriği dosya yoluyla değişir.",
        parameters=[_p("path", "Dosya yolu", required=True)],
    ),
    ToolDefinition(
        name="count_file_lines",
        display_name="Satır sayısı",
        description="İzinli bir metin dosyasındaki satır sayısını okur (2 MB tavan).",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Metin dosyası yolu", required=True)],
    ),
    ToolDefinition(
        name="create_directory",
        display_name="Klasör oluştur",
        description=(
            "İzin verilen kök altında klasör oluşturur. "
            "Kullanıcı 'yeni klasör oluştur / masaüstünde X klasörü yap' dediğinde kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Diskte yeni bir klasör oluşur.",
        parameters=[_p("path", "Klasör yolu veya desktop/ad, documents/ad", required=True)],
    ),
    ToolDefinition(
        name="get_file_info",
        display_name="Dosya bilgisi",
        description="Dosya veya klasörün boyutunu ve değişim tarihini okur. İçerik okumaz.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Dosya veya klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="get_special_folder_path",
        display_name="Özel klasör yolu",
        description="Masaüstü/Belgeler/İndirilenler/Resimler tam yolunu okur. Panoya yazmaz.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p(
                "folder",
                "Özel klasör",
                required=True,
                enum=["desktop", "documents", "downloads", "pictures"],
            ),
        ],
    ),
    ToolDefinition(
        name="get_folder_size",
        display_name="Klasör boyutu",
        description=(
            "İzinli bir klasörün toplam boyutunu okur. "
            "Kullanıcı 'masaüstü ne kadar yer kaplıyor' dediğinde kullan. "
            "Disk doluluğu için get_disk_usage kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu veya desktop/documents/downloads/pictures", required=True)],
    ),
    ToolDefinition(
        name="list_files_by_extension",
        display_name="Uzantıya göre listele",
        description=(
            "İzinli klasörde belirli uzantılı dosyaları listeler. "
            "Kullanıcı 'masaüstündeki pdf'leri listele' dediğinde kullan. "
            "Kaç dosya için list_directory, ara için search_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", required=True),
            _p("extension", "Uzantı (pdf, txt, jpg…)", required=True),
        ],
    ),
    ToolDefinition(
        name="get_newest_file",
        display_name="En yeni dosya",
        description=(
            "Klasördeki en son değişen tek dosyayı okur. "
            "Kullanıcı 'en son indirilen dosya' dediğinde kullan. "
            "Liste için list_recent_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="is_directory_empty",
        display_name="Klasör boş mu",
        description="İzinli klasörün boş olup olmadığını sorar. Geri dönüşümü boşaltmaz.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="get_largest_file",
        display_name="En büyük dosya",
        description=(
            "Klasördeki en büyük tek dosyayı okur. "
            "Kullanıcı 'masaüstünde en büyük dosya' dediğinde kullan. "
            "Klasör boyutu için get_folder_size, en yeni için get_newest_file kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="count_files_by_extension",
        display_name="Uzantı sayısı",
        description=(
            "İzinli klasörde belirli uzantılı dosya sayısını verir. "
            "Kullanıcı 'masaüstünde kaç pdf' dediğinde kullan. "
            "Liste için list_files_by_extension, kaç dosya için list_directory kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", required=True),
            _p("extension", "Uzantı (pdf, txt, jpg…)", required=True),
        ],
    ),
    ToolDefinition(
        name="list_subdirectories",
        display_name="Alt klasörler",
        description=(
            "İzinli klasördeki alt klasör adlarını listeler. "
            "Kullanıcı 'masaüstündeki klasörler' dediğinde kullan. "
            "Dosyalar için list_directory, yeni klasör için create_directory kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="list_today_files",
        display_name="Bugünkü dosyalar",
        description=(
            "Klasörde bugün değişen dosyaları listeler. "
            "Kullanıcı 'bugün indirilenler' dediğinde kullan. "
            "Son N için list_recent_files, en yeni tek dosya için get_newest_file kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", default="downloads"),
            _p("limit", "En fazla kayıt", type_="integer", default=20),
        ],
    ),
    ToolDefinition(
        name="get_oldest_file",
        display_name="En eski dosya",
        description=(
            "Klasördeki en eski tek dosyayı okur. "
            "Kullanıcı 'masaüstünde en eski dosya' dediğinde kullan. "
            "En yeni için get_newest_file, en büyük için get_largest_file kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="count_subdirectories",
        display_name="Klasör sayısı",
        description=(
            "İzinli klasördeki alt klasör sayısını verir. "
            "Kullanıcı 'masaüstünde kaç klasör' dediğinde kullan. "
            "Liste için list_subdirectories, kaç dosya için list_directory kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="get_smallest_file",
        display_name="En küçük dosya",
        description=(
            "Klasördeki en küçük tek dosyayı okur. "
            "Kullanıcı 'masaüstünde en küçük dosya' dediğinde kullan. "
            "En büyük için get_largest_file kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="list_this_week_files",
        display_name="Bu haftaki dosyalar",
        description=(
            "Klasörde bu hafta değişen dosyaları listeler. "
            "Kullanıcı 'bu hafta indirilenler' dediğinde kullan. "
            "Bugün için list_today_files, son N için list_recent_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", default="downloads"),
            _p("limit", "En fazla kayıt", type_="integer", default=20),
        ],
    ),
    ToolDefinition(
        name="list_yesterday_files",
        display_name="Dünkü dosyalar",
        description=(
            "Klasörde dün değişen dosyaları listeler. "
            "Kullanıcı 'dün indirilenler' dediğinde kullan. "
            "Bugün için list_today_files, bu hafta için list_this_week_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", default="downloads"),
            _p("limit", "En fazla kayıt", type_="integer", default=20),
        ],
    ),
    ToolDefinition(
        name="count_today_files",
        display_name="Bugünkü dosya sayısı",
        description=(
            "Klasörde bugün değişen dosya sayısını verir. "
            "Kullanıcı 'bugün kaç dosya indirildi' dediğinde kullan. "
            "Liste için list_today_files, kaç dosya için list_directory kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="list_this_month_files",
        display_name="Bu ayki dosyalar",
        description=(
            "Klasörde bu ay değişen dosyaları listeler. "
            "Kullanıcı 'bu ay indirilenler' dediğinde kullan. "
            "Bu hafta için list_this_week_files, dün için list_yesterday_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", default="downloads"),
            _p("limit", "En fazla kayıt", type_="integer", default=20),
        ],
    ),
    ToolDefinition(
        name="count_yesterday_files",
        display_name="Dünkü dosya sayısı",
        description=(
            "Klasörde dün değişen dosya sayısını verir. "
            "Kullanıcı 'dün kaç dosya indirildi' dediğinde kullan. "
            "Liste için list_yesterday_files, bugün sayı için count_today_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="count_this_week_files",
        display_name="Bu haftaki dosya sayısı",
        description=(
            "Klasörde bu hafta değişen dosya sayısını verir. "
            "Kullanıcı 'bu hafta kaç dosya indirildi' dediğinde kullan. "
            "Liste için list_this_week_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="count_this_month_files",
        display_name="Bu ayki dosya sayısı",
        description=(
            "Klasörde bu ay değişen dosya sayısını verir. "
            "Kullanıcı 'bu ay kaç dosya indirildi' dediğinde kullan. "
            "Liste için list_this_month_files kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Klasör yolu", required=True)],
    ),
    ToolDefinition(
        name="list_recent_files",
        display_name="Son dosyalar",
        description=(
            "Bir özel klasördeki en son değişen dosyaları listeler. "
            "Kullanıcı 'son indirilenler / son dosyalar' dediğinde kullan."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[
            _p("path", "Klasör yolu veya desktop/documents/downloads/pictures", default="downloads"),
            _p("limit", "En fazla kayıt", type_="integer", default=8),
        ],
    ),
    ToolDefinition(
        name="show_in_folder",
        display_name="Gezginde göster",
        description=(
            "Dosya veya klasörü Windows Gezgini'nde seçili gösterir. "
            "Kullanıcı 'gezginde göster' dediğinde kullan. Kabuk yok."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Gezgin penceresi açılır.",
        parameters=[_p("path", "Dosya veya klasör yolu", required=True)],
    ),

    ToolDefinition(
        name="search_files",
        display_name="Dosya ara",
        description=(
            "İzin verilen klasörlerde dosya adına göre arama yapar. "
            "Joker karakter (*) desteklenir."
        ),
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Yalnızca okuma yapar.",
        parameters=[
            _p("query", "Aranacak dosya adı deseni (ör. *.pdf, rapor*)", required=True),
            _p("root", "Arama yapılacak kök klasör (isteğe bağlı)"),
            _p("limit", "En fazla sonuç sayısı", type_="integer", default=50),
        ],
    ),
    ToolDefinition(
        name="read_file",
        display_name="Dosya oku",
        description="İzin verilen bir klasördeki metin dosyasının içeriğini okur.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        impact="Yalnızca okuma yapar.",
        parameters=[
            _p("path", "Dosya yolu", required=True),
            _p("max_chars", "Okunacak en fazla karakter", type_="integer", default=20000),
        ],
    ),
    ToolDefinition(
        name="create_file",
        display_name="Dosya oluştur",
        description="İzin verilen bir klasörde yeni metin dosyası oluşturur.",
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Diskte yeni bir dosya oluşturulur. Var olan dosyanın üzerine yazılmaz.",
        parameters=[
            _p("path", "Oluşturulacak dosya yolu", required=True),
            _p("content", "Dosya içeriği", required=True),
        ],
    ),
    ToolDefinition(
        name="save_selected_text",
        display_name="Seçimi dosyaya kaydet",
        description=(
            "Odaktaki seçili metni veya panoyu izinli bir klasöre kaydeder. "
            "Panoyu ezmez, Ctrl+C kullanmaz. create üzerine yazmaz. "
            "Kullanıcı 'şunu kaydet / panodakini kaydet / şunu not al' dediğinde kullan."
        ),
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Diskte yeni bir metin dosyası oluşur veya var olana eklenir.",
        parameters=[
            _p("path", "Dosya yolu veya desktop/ad.txt (boşsa zaman damgalı ad)"),
            _p("folder", "Özel klasör: desktop/documents/downloads/pictures", default="desktop"),
            _p("source", "selection veya clipboard", enum=["selection", "clipboard"], default="selection"),
            _p("mode", "create üzerine yazmaz; append sona ekler", enum=["create", "append"], default="create"),
        ],
    ),
    ToolDefinition(
        name="edit_file",
        display_name="Dosya düzenle",
        description=(
            "Var olan bir metin dosyasını düzenler. mode='replace' tüm içeriği "
            "değiştirir, mode='append' sona ekler."
        ),
        category="filesystem",
        risk=MEDIUM,
        execution=HOST,
        impact="Var olan dosyanın içeriği değişir. Yedek (.bak) oluşturulur.",
        parameters=[
            _p("path", "Dosya yolu", required=True),
            _p("content", "Yazılacak içerik", required=True),
            _p("mode", "Yazma modu", enum=["replace", "append"], default="append"),
        ],
    ),
    ToolDefinition(
        name="delete_file",
        display_name="Dosya sil",
        description="İzin verilen bir klasördeki dosyayı Geri Dönüşüm Kutusu'na taşır.",
        category="filesystem",
        risk=HIGH,
        execution=HOST,
        impact="Dosya Geri Dönüşüm Kutusu'na taşınır. Kalıcı silme yapılmaz.",
        parameters=[_p("path", "Silinecek dosya yolu", required=True)],
    ),

    ToolDefinition(
        name="get_cpu_usage",
        display_name="CPU kullanımı",
        description="Anlık işlemci kullanım yüzdesini ve çekirdek bilgisini getirir.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_ram_usage",
        display_name="RAM kullanımı",
        description="Toplam ve kullanılan bellek miktarını getirir.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_gpu_usage",
        display_name="GPU kullanımı",
        description="NVIDIA GPU modelini, VRAM kullanımını ve sıcaklığını getirir.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_disk_usage",
        display_name="Disk kullanımı",
        description="Disk bölümlerinin doluluk oranını getirir.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_processes",
        display_name="Çalışan işlemler",
        description="En çok bellek kullanan işlemleri listeler.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("limit", "Listelenecek işlem sayısı", type_="integer", default=15)],
    ),
    ToolDefinition(
        name="is_process_running",
        display_name="Süreç çalışıyor mu",
        description=(
            "Allowlist uygulamasının çalışıp çalışmadığını sorar. "
            "Listelemez, sonlandırmaz. Kullanıcı 'chrome çalışıyor mu' dediğinde kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("name", "Uygulama takma adı (chrome, notepad, vscode…)", required=True)],
    ),
    ToolDefinition(
        name="kill_process",
        display_name="İşlem sonlandır",
        description="Verilen PID'e sahip işlemi zorla sonlandırır.",
        category="system",
        risk=HIGH,
        execution=HOST,
        impact="İşlem zorla kapatılır; kaydedilmemiş veriler kaybolur.",
        parameters=[_p("pid", "İşlem kimliği (PID)", type_="integer", required=True)],
    ),
    ToolDefinition(
        name="set_volume",
        display_name="Ses seviyesi ayarla",
        description=(
            "Windows ana ses seviyesini 0-100 arasında ayarlar. "
            "Kullanıcı 'sesi kıs/aç/kapat' veya 'sesi yüzde 30 yap' dediğinde kullan."
        ),
        category="system",
        risk=MEDIUM,
        execution=HOST,
        impact="Sistem ses seviyesi değişir.",
        parameters=[_p("level", "Ses seviyesi (0-100)", type_="integer", required=True)],
    ),
    ToolDefinition(
        name="get_volume",
        display_name="Ses seviyesini oku",
        description="Windows ana ses seviyesini 0-100 arasında okur (değiştirmez).",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="take_screenshot",
        display_name="Ekran görüntüsü al",
        description="Ekranın görüntüsünü alır ve dosyaya kaydeder.",
        category="system",
        risk=MEDIUM,
        execution=HOST,
        impact="Ekranınızın görüntüsü alınır ve Resimler klasörüne kaydedilir.",
        parameters=[],
    ),
    ToolDefinition(
        name="clipboard_read",
        display_name="Panoyu oku",
        description="Windows panosundaki metni okur.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="clipboard_write",
        display_name="Panoya yaz",
        description="Windows panosuna metin yazar.",
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Panonuzun mevcut içeriği değişir.",
        parameters=[_p("text", "Panoya yazılacak metin", required=True)],
    ),
    ToolDefinition(
        name="clipboard_clear",
        display_name="Panoyu temizle",
        description="Windows panosundaki metni siler. Kullanıcı 'panoyu temizle/boşalt' dediğinde kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Pano içeriği silinir.",
        parameters=[],
    ),
    ToolDefinition(
        name="copy_selected_text",
        display_name="Seçili metni kopyala",
        description=(
            "Odaktaki seçili metni panoya kopyalar (Ctrl+C kullanmaz; panoyu seçimle değiştirir). "
            "Kullanıcı 'şunu/bunu/seçiliyi kopyala' dediğinde kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Pano içeriği seçili metinle değişir.",
        parameters=[],
    ),
    ToolDefinition(
        name="lock_workstation",
        display_name="Oturumu kilitle",
        description=(
            "Windows oturumunu kilitler (Win+L). Kullanıcı bilgisayarı/ekranı kilitle dediğinde kullan."
        ),
        category="system",
        risk=MEDIUM,
        execution=HOST,
        impact="Ekran kilitlenir; oturumu açmak için parola gerekir.",
        parameters=[],
    ),
    ToolDefinition(
        name="get_selected_text",
        display_name="Seçili metni oku",
        description="Odaktaki penceredeki seçili/odak metnini okur (panoyu değiştirmez).",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_foreground_window",
        display_name="Ön plan penceresi",
        description="Odaktaki pencerenin başlığını ve PID'ini döndürür.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_open_windows",
        display_name="Açık pencereler",
        description="Açık pencere başlıklarını listeler. Tıklamaz, HWND vermez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("limit", "En fazla kaç pencere", type_="integer", default=20)],
    ),
    ToolDefinition(
        name="get_display_info",
        display_name="Ekran bilgisi",
        description="Bağlı ekranların çözünürlüğünü ve ölçeğini okur (fare/klavye yok).",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_idle_time",
        display_name="Boşta kalma süresi",
        description="Kullanıcının kaç saniyedir giriş yapmadığını döndürür.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_power_status",
        display_name="Güç / pil durumu",
        description=(
            "Cihazın prize takılı mı yoksa pille mi çalıştığını okur. "
            "Kullanıcı 'pil / şarj durumu' dediğinde kullan. Şarj etmez."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_battery_level",
        display_name="Pil yüzdesi",
        description=(
            "Pil şarj yüzdesini okur. Prize takılı mı diye sormak için get_power_status kullan. "
            "Kullanıcı 'pil yüzde kaç' dediğinde kullan. Şarj etmez."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_computer_info",
        display_name="Bilgisayar bilgisi",
        description="Ana makine adı, kullanıcı adı ve Windows sürümünü okur. Kabuk yok.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_system_locale",
        display_name="Sistem dili",
        description="Windows / uygulama yerelini okur. Ayar değiştirmez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_system_time",
        display_name="Yerel saat",
        description="Bilgisayarın yerel tarih ve saatini okur. Ayar değiştirmez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_dark_mode",
        display_name="Karanlık mod",
        description="Windows uygulama temasının koyu olup olmadığını okur. Değiştirmez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_internet_status",
        display_name="İnternet var mı",
        description="DNS ile bağlantı olup olmadığını sorar. IP/parola okumaz.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_startup_apps",
        display_name="Başlangıç programları",
        description="Kullanıcı başlangıç (HKCU Run) adlarını listeler. Açmaz, silmez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_default_browser",
        display_name="Varsayılan tarayıcı",
        description="HTTPS için varsayılan tarayıcıyı okur. Açmaz.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_removable_drives",
        display_name="USB / çıkarılabilir sürücüler",
        description="Takılı USB/SD sürücülerini listeler. Biçimlendirmez, çıkarmaz.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_logical_drives",
        display_name="Sürücü harfleri",
        description=(
            "Tüm mantıksal sürücüleri listeler. USB-only list_removable_drives değil. "
            "Biçimlendirmez. Kullanıcı 'sürücüleri listele' dediğinde kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="eject_removable_drive",
        display_name="USB çıkar",
        description=(
            "Yalnızca çıkarılabilir (DriveType=2) sürücü harfini güvenle çıkarır. "
            "Biçimlendirmez. Kullanıcı 'E sürücüsünü çıkar' dediğinde kullan."
        ),
        category="system",
        risk=MEDIUM,
        execution=HOST,
        impact="USB/SD sürücüsü güvenle çıkarılır; veri yazılmaz.",
        parameters=[_p("letter", "Sürücü harfi (A–Z)", required=True)],
    ),
    ToolDefinition(
        name="list_printers",
        display_name="Yazıcılar",
        description="Kurulu yazıcıları listeler. Yazdırmaz, kuyruk silmez.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_default_printer",
        display_name="Varsayılan yazıcı",
        description="Varsayılan yazıcının adını okur. Yazdırmaz. Liste için list_printers kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_file_association",
        display_name="Dosya ilişkilendirmesi",
        description="İzinli bir uzantıyı hangi programın açtığını okur. Dosya açmaz.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("extension", "Uzantı (pdf, txt, jpg…)", required=True)],
    ),
    ToolDefinition(
        name="get_power_plan",
        display_name="Güç planı",
        description="Aktif Windows güç planının adını okur. Değiştirmez. Pil için get_power_status kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_user_profile_path",
        display_name="Kullanıcı klasörü",
        description="Kullanıcı ev klasörünün yolunu okur. Masaüstü yolu için get_special_folder_path kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_uptime",
        display_name="Açık kalma süresi",
        description=(
            "Bilgisayarın ne zamandır açık olduğunu okur. "
            "Kullanıcı 'ne zamandır açık / uptime' dediğinde kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_wifi_status",
        display_name="Wi-Fi durumu",
        description=(
            "Bağlı kablosuz ağın adını (SSID) okur. Parola okumaz. "
            "Kullanıcı 'wifi adı / hangi ağa bağlıyım' dediğinde kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_nearby_wifi",
        display_name="Yakındaki Wi-Fi",
        description="Görünen kablosuz ağ adlarını (SSID) listeler. Parola/BSSID okumaz.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_last_boot_time",
        display_name="Son açılış",
        description=(
            "Bilgisayarın son açılış zamanını okur. "
            "Kullanıcı 'son açılış ne zaman' dediğinde kullan. "
            "Süre için get_uptime kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_system_model",
        display_name="Bilgisayar modeli",
        description=(
            "Marka ve model adını okur. "
            "Kullanıcı 'bilgisayar modeli' dediğinde kullan. "
            "Ad/kullanıcı için get_computer_info kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_night_light",
        display_name="Gece ışığı",
        description="Gece ışığının açık olup olmadığını okur. Karanlık tema için get_dark_mode kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_bluetooth_status",
        display_name="Bluetooth durumu",
        description=(
            "Bluetooth radyosunun var/açık olup olmadığını okur. "
            "Kullanıcı 'bluetooth açık mı' dediğinde kullan. "
            "Ayar sayfası için open_windows_settings kullan. Eşleştirmez."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_timezone",
        display_name="Saat dilimi",
        description="IANA saat dilimini okur. Saat için get_system_time kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_temp_folder_path",
        display_name="Geçici klasör",
        description="Geçici klasör yolunu okur. Ev klasörü için get_user_profile_path kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_wallpaper_path",
        display_name="Duvar kağıdı",
        description="Duvar kağıdı dosya yolunu okur. Görüntüyü açmaz. Ekran görüntüsü için take_screenshot kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_wifi_radio",
        display_name="Wi-Fi radyo",
        description=(
            "Wi-Fi radyosunun açık olup olmadığını okur. "
            "Kullanıcı 'wifi açık mı' dediğinde kullan. "
            "SSID için get_wifi_status, yakın ağlar için list_nearby_wifi kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_default_playback_device",
        display_name="Varsayılan hoparlör",
        description="Varsayılan ses çıkış aygıtının adını okur. Ses seviyesi için get_volume kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_drive_label",
        display_name="Sürücü etiketi",
        description=(
            "Mantıksal sürücünün etiketini okur. "
            "Kullanıcı 'C sürücüsünün adı' dediğinde kullan. "
            "Çıkarmaz; doluluk için get_disk_usage kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("letter", "Sürücü harfi (C)", default="C")],
    ),
    ToolDefinition(
        name="get_onedrive_path",
        display_name="OneDrive klasörü",
        description="OneDrive klasör yolunu okur. Ev klasörü için get_user_profile_path kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_cpu_name",
        display_name="İşlemci adı",
        description="İşlemci model adını okur. Kullanım için get_cpu_usage kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_gpu_name",
        display_name="Ekran kartı adı",
        description="Ekran kartı adını okur. Kullanım/sıcaklık için get_gpu_usage kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_ethernet_status",
        display_name="Ethernet durumu",
        description=(
            "Kablolu ağın bağlı olup olmadığını okur. "
            "Wi-Fi için get_wifi_status, IP için get_network_interfaces kullan."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_default_recording_device",
        display_name="Varsayılan mikrofon",
        description="Varsayılan mikrofon adını okur. Hoparlör için get_default_playback_device kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_refresh_rate",
        display_name="Yenileme hızı",
        description="Birincil ekranın Hz değerini okur. Monitör sayısı için get_display_info kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_screen_scale",
        display_name="Ekran ölçeği",
        description="Birincil ekranın ölçek yüzdesini okur. Hz için get_refresh_rate, monitör sayısı için get_display_info kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_ram_size",
        display_name="RAM kapasitesi",
        description="Toplam bellek miktarını okur. Kullanım yüzdesi için get_ram_usage kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_cpu_count",
        display_name="Çekirdek sayısı",
        description="İşlemci çekirdek sayısını okur. Ad için get_cpu_name, kullanım için get_cpu_usage kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_mute_status",
        display_name="Ses kapalı mı",
        description="Sessiz olup olmadığını okur. Seviye için get_volume, sessiz yapmak için set_volume kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_drive_filesystem",
        display_name="Dosya sistemi",
        description="Sürücünün dosya sistemini (NTFS/FAT) okur. Etiket için get_drive_label, doluluk için get_disk_usage kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[_p("letter", "Sürücü harfi (C)", default="C")],
    ),
    ToolDefinition(
        name="get_airplane_mode",
        display_name="Uçak modu",
        description="Uçak modunun açık olup olmadığını okur. Wi-Fi radyo için get_wifi_radio kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="list_calendar_events",
        display_name="Takvim olayları",
        description=(
            "Klasik Outlook COM ile varsayılan takvim klasörünü salt okunur listeler. "
            "Graph / New Outlook / schtasks yok. Gövde dönmez. "
            "Ne zaman: takvim, randevu, ajanda. "
            "Ne zaman değil: görev listesi → list_processes; yarın ne yapmalıyım anlatı."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Outlook takvimi salt okunur okunur; yoksa found=false.",
        parameters=[
            _p("days", "İleri kaç gün (1-31)", type_="integer", default=7),
            _p("limit", "En fazla olay", type_="integer", default=20),
        ],
    ),
    ToolDefinition(
        name="list_outlook_tasks",
        display_name="Outlook görevleri",
        description=(
            "Klasik Outlook COM görev klasörünü salt okunur listeler. Gövde yok. "
            "Ne zaman: outlook görevlerim. Ne zaman değil: görev listesi → list_processes."
        ),
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Outlook görevleri salt okunur okunur; yoksa found=false.",
        parameters=[_p("limit", "En fazla görev", type_="integer", default=20)],
    ),
    ToolDefinition(
        name="get_os_version",
        display_name="Windows sürümü",
        description="İşletim sistemi sürümünü okur. Model için get_system_model, ad için get_computer_info kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_username",
        display_name="Kullanıcı adı",
        description="Oturum kullanıcı adını okur. Ev klasörü için get_user_profile_path kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_brightness",
        display_name="Parlaklık",
        description="Ekran parlaklığını okur. Ölçek için get_screen_scale, gece ışığı için get_night_light kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_vpn_status",
        display_name="VPN durumu",
        description="VPN bağlı mı okur. Wi-Fi için get_wifi_status, ethernet için get_ethernet_status kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_keyboard_layout",
        display_name="Klavye dili",
        description="Aktif klavye dilini okur. Sistem dili için get_system_locale kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_battery_saver",
        display_name="Pil tasarrufu",
        description="Pil tasarrufunun açık olup olmadığını okur. Yüzde için get_battery_level, plan için get_power_plan kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_architecture",
        display_name="Sistem mimarisi",
        description="64/32 bit mimariyi okur. Sürüm için get_os_version, işlemci adı için get_cpu_name kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_focus_assist",
        display_name="Odaklanma yardımı",
        description="Odaklanma / rahatsız etme durumunu okur. Sessiz için get_mute_status, gece ışığı için get_night_light kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_firewall_status",
        display_name="Güvenlik duvarı",
        description="Windows güvenlik duvarının açık olup olmadığını okur.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_default_mail_app",
        display_name="Varsayılan e-posta",
        description="Varsayılan e-posta uygulamasını okur. Tarayıcı için get_default_browser kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_screenshots_folder",
        display_name="Ekran görüntüleri klasörü",
        description="Ekran Görüntüleri klasör yolunu okur. Ekran yakalamak için take_screenshot kullan.",
        category="filesystem",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_wifi_signal",
        display_name="Wi-Fi sinyali",
        description="Bağlı Wi-Fi sinyal yüzdesini okur. SSID için get_wifi_status, radyo için get_wifi_radio kullan.",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="get_network_interfaces",
        display_name="Ağ arayüzleri",
        description="Host'un harici IPv4/IPv6 adreslerini listeler (MAC yok).",
        category="system",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="notify_user",
        display_name="Masaüstü bildirimi",
        description="Windows Action Center'da kısa bir bildirim gösterir (dakikada en fazla 3).",
        category="system",
        risk=LOW,
        execution=HOST,
        impact="Görev çubuğunda bir bildirim görünür.",
        parameters=[
            _p("title", "Bildirim başlığı", default="Uryx"),
            _p("body", "Bildirim metni", required=True),
        ],
    ),
    ToolDefinition(
        name="get_docker_engine_status",
        display_name="Docker motor tanısı",
        description="Host'taki Docker Desktop motorunu, compose servislerini ve ipuçlarını okur.",
        category="docker",
        risk=LOW,
        execution=HOST,
        parameters=[],
    ),
    ToolDefinition(
        name="open_docker_desktop",
        display_name="Docker Desktop'ı aç",
        description="Docker Desktop'ı CLI veya exe ile host'ta başlatır.",
        category="docker",
        risk=MEDIUM,
        execution=HOST,
        impact="Docker Desktop uygulaması açılır ve motor ayağa kalkabilir.",
        parameters=[],
    ),
    ToolDefinition(
        name="get_docker_desktop_logs",
        display_name="Docker Desktop logları",
        description="Host'ta `docker desktop logs` çalıştırır (follow yok, satır tavanı var).",
        category="docker",
        risk=LOW,
        execution=HOST,
        parameters=[_p("lines", "Son kaç satır", type_="integer", default=200)],
    ),

    ToolDefinition(
        name="git_status",
        display_name="Git durumu",
        description="Verilen depo klasöründe 'git status' çalıştırır.",
        category="git",
        risk=LOW,
        execution=HOST,
        parameters=[_p("path", "Git deposu klasörü", required=True)],
    ),
    ToolDefinition(
        name="git_commit",
        display_name="Git commit",
        description="Değişiklikleri stage'leyip commit oluşturur.",
        category="git",
        risk=HIGH,
        execution=HOST,
        impact="Depoda yeni bir commit oluşturulur.",
        parameters=[
            _p("path", "Git deposu klasörü", required=True),
            _p("message", "Commit mesajı", required=True),
        ],
    ),
    ToolDefinition(
        name="git_push",
        display_name="Git push",
        description="Commit'leri uzak depoya gönderir.",
        category="git",
        risk=HIGH,
        execution=HOST,
        impact="Yerel commit'ler uzak depoya gönderilir. Bu işlem dışarıya açıktır.",
        parameters=[
            _p("path", "Git deposu klasörü", required=True),
            _p("remote", "Uzak depo adı", default="origin"),
            _p("branch", "Dal adı (boşsa aktif dal)"),
        ],
    ),

    ToolDefinition(
        name="run_powershell",
        display_name="PowerShell komutu çalıştır",
        description=(
            "Kısıtlı bir PowerShell komutu çalıştırır. Komut, izin verilen cmdlet "
            "listesinden başlamalıdır; boru hattı ve yönlendirme reddedilir."
        ),
        category="shell",
        risk=HIGH,
        execution=HOST,
        impact="Bilgisayarınızda bir sistem komutu çalıştırılır.",
        parameters=[
            _p("command", "Çalıştırılacak PowerShell komutu", required=True),
            _p("cwd", "Çalışma klasörü (isteğe bağlı)"),
        ],
    ),
    ToolDefinition(
        name="run_cmd",
        display_name="CMD komutu çalıştır",
        description=(
            "Kısıtlı bir CMD komutu çalıştırır. Yalnızca izin listesindeki komutlar "
            "kabul edilir (dir, ipconfig, ping, systeminfo, tasklist, where, echo)."
        ),
        category="shell",
        risk=HIGH,
        execution=HOST,
        impact="Bilgisayarınızda bir sistem komutu çalıştırılır.",
        parameters=[
            _p("command", "Çalıştırılacak CMD komutu", required=True),
            _p("cwd", "Çalışma klasörü (isteğe bağlı)"),
        ],
    ),

    ToolDefinition(
        name="docker_list_containers",
        display_name="Docker konteynerlerini listele",
        description="Docker konteynerlerini ve durumlarını listeler.",
        category="docker",
        risk=LOW,
        execution=BACKEND,
        parameters=[
            _p("all", "Durdurulmuş konteynerleri de göster", type_="boolean", default=True)
        ],
    ),
    ToolDefinition(
        name="docker_start_container",
        display_name="Docker konteyneri başlat",
        description="Adı verilen Docker konteynerini başlatır.",
        category="docker",
        risk=MEDIUM,
        execution=BACKEND,
        impact="Konteyner başlatılır ve sistem kaynağı kullanmaya başlar.",
        parameters=[_p("name", "Konteyner adı veya kimliği", required=True)],
    ),
    ToolDefinition(
        name="docker_stop_container",
        display_name="Docker konteyneri durdur",
        description="Adı verilen Docker konteynerini durdurur.",
        category="docker",
        risk=MEDIUM,
        execution=BACKEND,
        impact="Konteyner durur; bağlı servisler kullanılamaz hâle gelir.",
        parameters=[_p("name", "Konteyner adı veya kimliği", required=True)],
    ),
    ToolDefinition(
        name="docker_remove_container",
        display_name="Docker konteyneri sil",
        description="Durdurulmuş bir Docker konteynerini siler.",
        category="docker",
        risk=HIGH,
        execution=BACKEND,
        impact="Konteyner kalıcı olarak silinir. Named volume'lar korunur.",
        parameters=[_p("name", "Konteyner adı veya kimliği", required=True)],
    ),
    ToolDefinition(
        name="docker_container_logs",
        display_name="Docker logları",
        description="Bir konteynerin son log satırlarını getirir.",
        category="docker",
        risk=LOW,
        execution=BACKEND,
        parameters=[
            _p("name", "Konteyner adı veya kimliği", required=True),
            _p("lines", "Satır sayısı", type_="integer", default=50),
        ],
    ),

    ToolDefinition(
        name="web_search",
        display_name="İnternette ara",
        description=(
            "İnternette güncel bilgi araştırır ve kaynak bağlantıları döndürür. "
            "Ne zaman: sürüm, fiyat, kişi, ürün, tanım veya kullanıcının özellikle "
            "araştırılmasını istediği genel konular. "
            "Ne zaman değil: manşet/haber listesi → web_news; ansiklopedi maddesi → "
            "wiki_lookup; bilinen http(s) adresi → web_fetch; JS/çerez/giriş → "
            "browser_open; sayısal hesap/birim → calculate."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete yalnızca arama sorgusu gönderilir.",
        parameters=[
            _p("query", "Araştırılacak açık ve kısa sorgu", required=True),
            _p("max_results", "En fazla sonuç sayısı", type_="integer", default=5),
            _p(
                "region",
                "DDG kl bölgesi. TR tr-tr (varsayılan); dünya wt-wt.",
                enum=["tr-tr", "wt-wt", "us-en", "uk-en", "de-de"],
                default="tr-tr",
            ),
            _p(
                "timelimit",
                "İsteğe bağlı zaman penceresi: d=gün, w=hafta, m=ay, y=yıl. Boş = filtresiz.",
                enum=["d", "w", "m", "y"],
            ),
            _p(
                "site",
                "İsteğe bağlı genel alan adı (wikipedia.org). site: operatörü buradan üretilir; "
                "sorguya elle site: yazma. Yerel/IP yok.",
            ),
            _p(
                "filetype",
                "İsteğe bağlı dosya türü. PDF/doküman ararken kullan.",
                enum=["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "html"],
            ),
            _p(
                "exclude_site",
                "Hariç tutulacak genel alan (pinterest.com). -site: buradan üretilir; "
                "sorguya elle yazma. site ile aynı olamaz.",
            ),
        ],
    ),
    ToolDefinition(
        name="web_research",
        display_name="Çok kaynaklı araştır",
        description=(
            "Güncel veya kapsamlı bir konuda farklı sorgu varyantlarını paralel çalıştırır, "
            "sonuçları URL bazında tekilleştirir ve kaynak çeşitliliği olan bir kanıt seti "
            "döndürür. "
            "Ne zaman: araştır, tara, karşılaştır, zamana duyarlı iddia. "
            "Ne zaman değil: tek basit sorgu → web_search; manşet listesi → web_news; "
            "ansiklopedi maddesi → wiki_lookup; döviz → fx_rate; hava → weather."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete birbiriyle ilişkili birkaç salt-okunur arama sorgusu gönderilir.",
        parameters=[
            _p("query", "Araştırılacak açık soru veya konu", required=True),
            _p("max_results", "En fazla tekil kanıt sayısı", type_="integer", default=10),
        ],
    ),
    ToolDefinition(
        name="web_social_profile",
        display_name="Resmi sosyal profili doğrula",
        description=(
            "Bir kişi veya markanın resmi Instagram hesabını bağımsız web kanıtlarıyla "
            "eşleştirir ve arama motorunda indekslenen en yeni gönderi adresini tarih sırasıyla "
            "çözer. Yanlış veya hayran hesaplarını elemek için sosyal gönderi isteklerinde kullan."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete kişi veya marka adıyla salt-okunur arama sorguları gönderilir.",
        parameters=[_p("query", "Kişi/marka ve sosyal gönderi isteği", required=True)],
    ),
    ToolDefinition(
        name="web_image_search",
        display_name="İnternette görsel ara",
        description=(
            "İnternette güncel görseller arar ve sohbet içinde gösterilecek bir galeri döndürür. "
            "Kullanıcı bir kişinin, ürünün, yerin veya konunun fotoğrafını/görselini görmek "
            "istediğinde bu aracı kullan."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete yalnızca görsel arama sorgusu gönderilir.",
        parameters=[
            _p(
                "query",
                "Görseli aranacak açık özne. Sosyal medya isteğinde kişi/hesap adı zorunludur; "
                "örnek: 'Sydney Sweeney Instagram latest post'. Öznesiz "
                "'Instagram latest post' yazma.",
                required=True,
            ),
            _p("max_results", "En fazla görsel sayısı", type_="integer", default=6),
        ],
    ),
    ToolDefinition(
        name="web_video_search",
        display_name="İnternette video ara",
        description=(
            "YouTube ve diğer genel video kaynaklarında video arar; doğrulanmış bağlantıları ve "
            "küçük resimleri masaüstündeki merkez medya panelinde gösterir. Kullanıcı video/klip "
            "getir, göster, bul veya ara dediğinde bunu kullan; kullanım talimatı yazma."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete yalnızca video arama sorgusu gönderilir.",
        parameters=[
            _p("query", "Aranacak video, sanatçı veya konu", required=True),
            _p("max_results", "En fazla video sayısı", type_="integer", default=6),
        ],
    ),
    ToolDefinition(
        name="web_news",
        display_name="Güncel haber ara",
        description=(
            "Yalnızca haber dizininde (başlık, özet, yayın tarihi, kaynak) arar. "
            "Ne zaman: haber, manşet, gündem, breaking, 'bugün ne oldu'. "
            "Ne zaman değil: ansiklopedi maddesi → wiki_lookup; tanım/nasıl yapılır → "
            "web_search; tek makale "
            "gövdesi → web_fetch; JS/giriş duvarı → browser_open; döviz/hesap → "
            "web_search veya calculate. "
            "Bölge: TR tr-tr (varsayılan), dünya wt-wt, ABD us-en, İngiltere uk-en, "
            "Almanya de-de. Kaynak daraltmak için source (aa.com.tr, reuters). "
            "Bugün/dün → timelimit=d."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete yalnızca haber arama sorgusu gönderilir.",
        parameters=[
            _p("query", "Haber konusu veya olay", required=True),
            _p("max_results", "En fazla haber sayısı", type_="integer", default=8),
            _p(
                "timelimit",
                "Zaman penceresi: d=gün, w=hafta, m=ay",
                enum=["d", "w", "m"],
                default="w",
            ),
            _p(
                "region",
                "DDG kl bölgesi. TR haber tr-tr; dünya manşeti wt-wt.",
                enum=["tr-tr", "wt-wt", "us-en", "uk-en", "de-de"],
                default="tr-tr",
            ),
            _p(
                "safesearch",
                "Güvenli arama: on, moderate, off",
                enum=["on", "moderate", "off"],
                default="moderate",
            ),
            _p(
                "source",
                "İsteğe bağlı kaynak daraltması: alan adı veya yayın adı (aa.com.tr, reuters)",
            ),
        ],
    ),
    ToolDefinition(
        name="web_fetch",
        display_name="Bağlantı metnini oku",
        description=(
            "Herkese açık bir http/https adresini oturumsuz çeker ve ana metni döndürür "
            "(HTML→düz metin). JavaScript çalıştırmaz, çerez göndermez, yerel/özel IP'ye "
            "gitmez. Kullanıcı bir link verdiğinde veya arama sonucundaki makaleyi okumak "
            "istediğinde browser_open yerine bunu kullan. Giriş, SPA veya dinamik sayfa ise "
            "browser_open + browser_read_page. Uzun sayfada truncated=true ise start_index ile "
            "devam et."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="İnternete salt-okunur bir GET isteği gider; yerel ağa çıkılmaz.",
        parameters=[
            _p("url", "Okunacak kesin HTTP/HTTPS adresi", required=True),
            _p(
                "max_chars",
                "Döndürülecek en fazla karakter",
                type_="integer",
                default=8000,
            ),
            _p(
                "start_index",
                "Önceki okuma kesildiyse devam indeksi",
                type_="integer",
                default=0,
            ),
        ],
    ),
    ToolDefinition(
        name="wiki_lookup",
        display_name="Wikipedia özeti",
        description=(
            "tr/en/de.wikipedia.org üzerindeki bir maddenin kısa özetini "
            "Wikimedia REST API ile okur. Kabuk, serbest URL veya web_fetch yoktur. "
            "Ne zaman: ansiklopedi, Wikipedia, 'kimdir', yerleşik tanım. "
            "Ne zaman değil: kelime/tanım → dict_lookup; güncel haber → web_news; "
            "sürüm/fiyat/güncel olay → web_search; kullanıcı belgesi → search_documents; "
            "rastgele http adresi → web_fetch."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Wikipedia'ya salt-okunur bir GET gider.",
        parameters=[
            _p("title", "Madde başlığı (ör. İstanbul, Alan Turing)", required=True),
            _p(
                "lang",
                "Viki dili. Türkçe tr; İngilizce en; Almanca de.",
                enum=["tr", "en", "de"],
                default="tr",
            ),
        ],
    ),
    ToolDefinition(
        name="dict_lookup",
        display_name="Sözlük tanımı",
        description=(
            "tr/en/de.wiktionary.org üzerindeki bir kelimenin tanımını Wikimedia REST "
            "ile okur. Kabuk, serbest URL veya wiki_lookup yoktur. "
            "Ne zaman: sözlük, 'ne demek', kelime anlamı, tanım. "
            "Ne zaman değil: ansiklopedi/kimdir → wiki_lookup; haber → web_news; "
            "ülke başkent/nüfus → country_info."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Wiktionary'ye salt-okunur bir GET gider.",
        parameters=[
            _p("term", "Kelime veya ifade (ör. merhaba, hello)", required=True),
            _p(
                "lang",
                "Sözlük dili. Türkçe tr; İngilizce en; Almanca de.",
                enum=["tr", "en", "de"],
                default="tr",
            ),
        ],
    ),
    ToolDefinition(
        name="browser_open",
        display_name="Web sayfasını aç",
        description=(
            "Uryx'in kalıcı ve güvenli tarayıcı oturumunda gerçek bir HTTP/HTTPS sayfası açar. "
            "Kullanıcı 'sayfasına gir', 'siteyi aç' veya özellikle bir sosyal medya profilini "
            "ziyaret et dediğinde genel web/görsel araması yerine bunu kullan. Profil adresi kesin "
            "değilse önce web_search ile resmi adresi bul. Oturum bilgileri sonraki açılışlarda "
            "korunur."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Uryx Web penceresinde genel bir internet sayfası açılır.",
        parameters=[
            _p("url", "Açılacak kesin HTTP/HTTPS adresi", required=True),
            _p(
                "wait_ms",
                "Dinamik içeriğin yüklenmesini bekleme süresi",
                type_="integer",
                default=2500,
            ),
            _p(
                "visible",
                "Sayfayı ayrı Uryx Web penceresinde göster; veri getirme işlerinde false",
                type_="boolean",
                default=True,
            ),
        ],
    ),
    ToolDefinition(
        name="open_external_url",
        display_name="Varsayılan tarayıcıda aç",
        description=(
            "Genel HTTP/HTTPS adresini Windows varsayılan tarayıcısında açar. "
            "Uryx Web oturumu değildir. Yerel/özel ağ ve file:// yok. "
            "Kullanıcı 'şu linki aç https://…' dediğinde kullan. "
            "Chrome'da ara → web_search; oturumlu sayfa → browser_open."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Varsayılan tarayıcıda bir sekme açılır.",
        parameters=[_p("url", "HTTP/HTTPS adresi", required=True)],
    ),
    ToolDefinition(
        name="browser_read_page",
        display_name="Web sayfasını oku",
        description=(
            "Uryx Web'de açık sayfanın görünen metnini, bağlantılarını ve büyük görsel "
            "sayısını okur. JavaScript veya giriş isteyen içerik için web_fetch yetmez; önce "
            "browser_open, sonra bunu kullan. Statik makale/dokümantasyon URL'si için web_fetch "
            "daha ucuz ve özel ağa gitmez."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Açık web sayfası salt okunur olarak incelenir.",
        parameters=[],
    ),
    ToolDefinition(
        name="browser_list_controls",
        display_name="Sayfa kontrollerini listele",
        description=(
            "Açık Uryx Web sayfasındaki görünür düğme, bağlantı ve form alanlarını indeksle "
            "listeler. Tıklamadan veya yazmadan önce bunu kullan. collectPageState yoktur. "
            "Ne zaman: forma yaz, kutuya yaz, butona tıkla. "
            "Ne zaman değil: yalnızca siteyi aç → browser_open; statik metin → browser_read_page."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Açık web sayfasındaki görünür kontroller salt okunur listelenir.",
        parameters=[],
    ),
    ToolDefinition(
        name="browser_click",
        display_name="Web öğesine tıkla",
        description=(
            "Uryx Web'deki görünür bir kontrole tıklar. index, browser_list_controls çıktısından "
            "gelir. CSS seçici, x/y veya serbest JavaScript yok. "
            "Ne zaman: listedeki buton/bağlantı. Ne zaman değil: siteyi aç → browser_open."
        ),
        category="web",
        risk=MEDIUM,
        execution=HOST,
        impact="Açık web sayfasında bir öğeye tıklanır.",
        parameters=[
            _p("index", "Kontrol indeksi (browser_list_controls)", type_="integer"),
            _p("role", "Erişilebilir rol (button, link, textbox)"),
            _p("name", "Erişilebilir ad veya görünür etiket"),
        ],
    ),
    ToolDefinition(
        name="browser_type",
        display_name="Web alanına yaz",
        description=(
            "Uryx Web'deki bir metin alanına yazar. Şifre tipi alanlar yasaktır. "
            "index, browser_list_controls çıktısından gelir. Metin en fazla 500 karakter."
        ),
        category="web",
        risk=MEDIUM,
        execution=HOST,
        impact="Açık web sayfasındaki bir alana metin yazılır.",
        parameters=[
            _p("index", "Kontrol indeksi", type_="integer", required=True),
            _p("text", "Yazılacak metin (en fazla 500 karakter)", required=True),
        ],
    ),
    ToolDefinition(
        name="browser_fill_form",
        display_name="Web formunu doldur",
        description=(
            "Birden fazla alanı tek onayda doldurur. fields[{index, text}]. "
            "İsteğe bağlı submit_index listedeki gönder düğmesi. Şifre alanı yok."
        ),
        category="web",
        risk=MEDIUM,
        execution=HOST,
        impact="Açık web sayfasındaki bir form doldurulur.",
        parameters=[
            _p("fields", "[{index, text}] alan listesi", type_="array", required=True),
            _p("submit_index", "Gönder düğmesi indeksi", type_="integer"),
        ],
    ),
    ToolDefinition(
        name="browser_scroll",
        display_name="Web sayfasını kaydır",
        description=(
            "Uryx Web'deki sayfayı kaydırır. Daha fazla gönderi veya içerik yüklemek için "
            "kullan; "
            "pozitif miktar aşağı, negatif miktar yukarı kaydırır."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Açık web sayfasının görünümü kaydırılır.",
        parameters=[
            _p("amount", "Piksel cinsinden kaydırma miktarı", type_="integer", default=700)
        ],
    ),
    ToolDefinition(
        name="browser_capture",
        display_name="Web sayfasını görüntüle",
        description=(
            "Yalnızca açık Uryx Web penceresinin görüntüsünü kaydeder ve sohbet içinde "
            "büyütülebilir önizleme olarak döndürür. Masaüstünün geri kalanını yakalamaz."
        ),
        category="web",
        risk=MEDIUM,
        execution=HOST,
        impact="Açık web sayfasının görünümü Resimler/Uryx/Web klasörüne kaydedilir.",
        parameters=[],
    ),
    ToolDefinition(
        name="browser_save_images",
        display_name="Sayfadaki görselleri getir",
        description=(
            "Uryx Web'de açık gerçek sayfanın DOM'unda bulunan büyük görselleri, mevcut oturum "
            "çerezlerini kullanarak indirir ve sohbet galerisinde gösterir. Kullanıcı 'oradaki "
            "fotoğrafları getir/göster' dediğinde browser_open sonrasında bunu kullan. İlgisiz "
            "web_image_search sonuçlarını sayfadaki içerikmiş gibi sunma."
        ),
        category="web",
        risk=LOW,
        execution=HOST,
        impact="Açık sayfadaki görseller Resimler/Uryx/Web klasörüne kaydedilir.",
        parameters=[
            _p(
                "max_results",
                "En fazla kaydedilecek görsel sayısı",
                type_="integer",
                default=6,
            ),
            _p(
                "required_text",
                "Yalnızca alt metninde bu kişi/konu adı geçen görselleri kaydet",
            ),
        ],
    ),
    ToolDefinition(
        name="weather",
        display_name="Hava durumu",
        description=(
            "Open-Meteo ile bir yerin güncel havasını ve 1–7 günlük tahmini okur. "
            "Anahtar yok, kabuk yok, serbest URL yok. "
            "Ne zaman: hava, sıcaklık, yağmur, rüzgâr, 'önümüzdeki günler'. "
            "Ne zaman değil: iklim tarihi/ansiklopedi → wiki_lookup; haber → web_news; "
            "görsel → web_image_search; resmi tatil → public_holidays; "
            "AQI/PM → air_quality; polen/alerji → pollen; namaz/ezan → prayer_times; "
            "gün doğumu/UV → sun_times; rakım → elevation."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Open-Meteo'ya salt-okunur GET gider.",
        parameters=[
            _p("place", "Şehir veya yer adı (İstanbul, Ankara)", required=True),
            _p(
                "days",
                "Günlük tahmin penceresi (1–7). Varsayılan 3.",
                type_="integer",
                default=3,
            ),
        ],
    ),
    ToolDefinition(
        name="air_quality",
        display_name="Hava kalitesi",
        description=(
            "Open-Meteo Air Quality ile bir yerin güncel Avrupa AQI, PM10/PM2.5, NO2 ve O3 "
            "değerini okur. Anahtar yok, kabuk yok. "
            "Ne zaman: hava kirliliği, AQI, partikül, 'hava kalitesi nasıl'. "
            "Ne zaman değil: sıcaklık/yağmur → weather; polen/alerji → pollen; "
            "haber → web_news."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Open-Meteo hava kalitesi API'sine GET gider.",
        parameters=[_p("place", "Şehir veya yer adı", required=True)],
    ),
    ToolDefinition(
        name="public_holidays",
        display_name="Resmi tatiller",
        description=(
            "Nager.Date (date.nager.at) ile bir ülkenin yıl bazlı resmi tatillerini okur. "
            "Anahtar yok, kabuk yok, serbest URL yok. "
            "Ne zaman: resmi tatil, bayram, '2026 Türkiye'de tatiller'. "
            "Ne zaman değil: hava → weather; takvim uygulaması açma → open_application; "
            "tarih/saat → prompt'taki İstanbul saati."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca date.nager.at'e salt-okunur GET gider.",
        parameters=[
            _p(
                "country",
                "ISO ülke kodu. TR varsayılan.",
                enum=[
                    "TR",
                    "DE",
                    "US",
                    "GB",
                    "FR",
                    "IT",
                    "ES",
                    "AT",
                    "NL",
                    "BE",
                    "CH",
                    "SE",
                    "NO",
                    "DK",
                    "PL",
                    "GR",
                    "PT",
                    "IE",
                    "FI",
                    "CZ",
                ],
                default="TR",
            ),
            _p("year", "Takvim yılı (2000–bu yıl+5)", type_="integer"),
        ],
    ),
    ToolDefinition(
        name="earthquakes",
        display_name="Depremler",
        description=(
            "USGS FDSN kataloğundan son 1–7 günün depremlerini okur. Anahtar yok, "
            "kabuk yok, serbest URL yok. Varsayılan: Türkiye kutusu. "
            "Ne zaman: son depremler, büyüklük, sismik. "
            "Ne zaman değil: deprem haberi/manşet → web_news; ansiklopedi → wiki_lookup."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca earthquake.usgs.gov'a salt-okunur GET gider.",
        parameters=[
            _p(
                "region",
                "tr = Türkiye kutusu; world = dünya (daha yüksek eşik).",
                enum=["tr", "world"],
                default="tr",
            ),
            _p(
                "minmagnitude",
                "En küçük büyüklük. TR varsayılan 3; dünya 5.",
                type_="number",
            ),
            _p(
                "days",
                "Geriye bakış (1–7). Varsayılan 2.",
                type_="integer",
                default=2,
            ),
        ],
    ),
    ToolDefinition(
        name="country_info",
        display_name="Ülke bilgisi",
        description=(
            "REST Countries (restcountries.com) ile başkent, nüfus, para birimi ve "
            "ISO kodunu okur. Anahtar yok, kabuk yok. "
            "Ne zaman: başkent, nüfus, ülke kodu, resmi adı. "
            "Ne zaman değil: tarihçe/kimdir → wiki_lookup; kur → fx_rate; "
            "resmi tatil → public_holidays; güncel haber → web_news."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca restcountries.com'a salt-okunur GET gider.",
        parameters=[
            _p("query", "Ülke adı veya ISO kodu (Türkiye, TR, DEU)", required=True),
        ],
    ),
    ToolDefinition(
        name="sun_times",
        display_name="Gün doğumu / UV",
        description=(
            "Open-Meteo ile bir yerin gün doğumu, gün batımı ve günlük UV tavanını okur. "
            "weather rewrite değildir; sıcaklık/yağmur için weather kullan. "
            "Ne zaman: gün doğumu, gün batımı, UV, 'güneş ne zaman'. "
            "Ne zaman değil: namaz/imsak → prayer_times; sıcaklık → weather; AQI → air_quality."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Open-Meteo'ya salt-okunur GET gider.",
        parameters=[
            _p("place", "Şehir veya yer adı", required=True),
            _p(
                "days",
                "Gün sayısı (1–3). Varsayılan 1.",
                type_="integer",
                default=1,
            ),
        ],
    ),
    ToolDefinition(
        name="prayer_times",
        display_name="Namaz vakitleri",
        description=(
            "Aladhan (api.aladhan.com) ile bir şehrin günlük namaz vakitlerini okur. "
            "Varsayılan hesap: Diyanet (13). Anahtar yok, kabuk yok. "
            "Ne zaman: namaz, ezan, imsak, iftar saati. "
            "Ne zaman değil: güneş/sıcaklık → weather; resmi tatil → public_holidays; "
            "takvim uygulaması → open_application."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca api.aladhan.com'a salt-okunur GET gider.",
        parameters=[
            _p("city", "Şehir (İstanbul, Ankara)", required=True),
            _p(
                "country",
                "ISO ülke kodu. TR varsayılan.",
                enum=["TR", "DE", "US", "GB", "FR", "NL", "AT", "BE", "SA", "AE"],
                default="TR",
            ),
            _p(
                "method",
                "13 = Diyanet; 3 = Muslim World League.",
                type_="integer",
                enum=["13", "3"],
                default=13,
            ),
            _p("date", "YYYY-MM-DD. Boşsa bugün (İstanbul)."),
        ],
    ),
    ToolDefinition(
        name="postal_lookup",
        display_name="Posta kodu",
        description=(
            "Zippopotam.us ile bir posta kodunun ilçe/şehir ve koordinatını okur. "
            "Anahtar yok, kabuk yok, serbest URL yok. "
            "Ne zaman: posta kodu, PK, ZIP, '34000 neresi'. "
            "Ne zaman değil: başkent/nüfus → country_info; hava → weather; "
            "adres geocode MCP → Ayarlar OSM kartı."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca api.zippopotam.us'a salt-okunur GET gider.",
        parameters=[
            _p("code", "Posta kodu (34000, 10115, SW1A)", required=True),
            _p(
                "country",
                "ISO ülke kodu. TR varsayılan.",
                enum=["TR", "DE", "US", "GB", "FR", "NL", "AT", "BE", "IT", "ES"],
                default="TR",
            ),
        ],
    ),
    ToolDefinition(
        name="iss_now",
        display_name="ISS konumu",
        description=(
            "Where the ISS at (api.wheretheiss.at) ile Uluslararası Uzay İstasyonu'nun "
            "anlık enlem, boylam ve irtifasını okur. Anahtar yok, kabuk yok. "
            "Ne zaman: ISS nerede, uzay istasyonu konumu. "
            "Ne zaman değil: uzay havası/kuzey ışığı → space_weather; "
            "ansiklopedi → wiki_lookup; kripto → web_search."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca api.wheretheiss.at'e salt-okunur GET gider.",
        parameters=[],
    ),
    ToolDefinition(
        name="space_weather",
        display_name="Uzay havası",
        description=(
            "NOAA SWPC (services.swpc.noaa.gov) R/S/G ölçeklerini okur. Anahtar yok. "
            "Ne zaman: uzay havası, jeomanyetik fırtına, aurora, güneş patlaması. "
            "Ne zaman değil: dünya havası → weather; ISS konumu → iss_now; "
            "AQI → air_quality."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca services.swpc.noaa.gov'a salt-okunur GET gider.",
        parameters=[],
    ),
    ToolDefinition(
        name="doi_lookup",
        display_name="DOI kaydı",
        description=(
            "Crossref (api.crossref.org) ile bir DOI'nin başlık, yazar ve yılını okur. "
            "Anahtar yok, kabuk yok. "
            "Ne zaman: DOI, makale künyesi, 10.xxxx/... "
            "Ne zaman değil: Wikipedia → wiki_lookup; arXiv MCP → mcp_call; "
            "PDF indir → yok."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca api.crossref.org'a salt-okunur GET gider.",
        parameters=[_p("doi", "DOI (10.1038/nphys1170 veya doi.org/…)", required=True)],
    ),
    ToolDefinition(
        name="elevation",
        display_name="Rakım",
        description=(
            "Open-Meteo Elevation ile bir yerin metre cinsinden rakımını okur. "
            "weather rewrite değildir. Anahtar yok. "
            "Ne zaman: rakım, yükseklik, 'kaç metre'. "
            "Ne zaman değil: sıcaklık → weather; ISS irtifa → iss_now; "
            "posta kodu → postal_lookup."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Open-Meteo'ya salt-okunur GET gider.",
        parameters=[_p("place", "Şehir, dağ veya yer adı", required=True)],
    ),
    ToolDefinition(
        name="pypi_lookup",
        display_name="PyPI paket",
        description=(
            "pypi.org JSON API ile bir Python paketinin sürüm ve özetini okur. "
            "İndirme yok, kabuk yok. "
            "Ne zaman: pip paketi, PyPI sürümü. "
            "Ne zaman değil: kod çalıştır → yok; npm → npm_lookup; "
            "kripto → web_search."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca pypi.org'a salt-okunur GET gider.",
        parameters=[_p("name", "Paket adı (httpx, ruff)", required=True)],
    ),
    ToolDefinition(
        name="ip_lookup",
        display_name="IP konumu",
        description=(
            "ipwho.is ile genel bir IPv4/IPv6 adresinin ülke, şehir ve ASN bilgisini okur. "
            "Özel/yerel IP yok; sunucu IP'si sorgulanmaz. "
            "Ne zaman: '8.8.8.8 nerede', genel IP konumu. "
            "Ne zaman değil: yerel/özel IP veya 'benim IP'm → get_network_interfaces; "
            "alan adı → dns_lookup; sayfa oku → web_fetch."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca ipwho.is'e salt-okunur GET gider.",
        parameters=[_p("ip", "Genel IPv4 veya IPv6", required=True)],
    ),
    ToolDefinition(
        name="food_barcode",
        display_name="Barkod / ürün",
        description=(
            "Open Food Facts ile bir EAN/UPC barkodunun ürün adı ve Nutri-Score'unu okur. "
            "Anahtar yok, yönlendirme yok. "
            "Ne zaman: barkod, EAN, GTIN, UPC. "
            "Ne zaman değil: Wikipedia → wiki_lookup; fiyat → web_search; "
            "QR/URL → web_search veya web_fetch."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca world.openfoodfacts.org'a salt-okunur GET gider.",
        parameters=[_p("barcode", "8–14 haneli barkod", required=True)],
    ),
    ToolDefinition(
        name="npm_lookup",
        display_name="npm paket",
        description=(
            "registry.npmjs.org ile bir npm paketinin sürüm ve özetini okur. İndirme yok. "
            "Ne zaman: npm paketi, node modülü sürümü. "
            "Ne zaman değil: PyPI → pypi_lookup; kod çalıştır → yok."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca registry.npmjs.org'a salt-okunur GET gider.",
        parameters=[_p("name", "Paket adı (react, @types/node)", required=True)],
    ),
    ToolDefinition(
        name="dns_lookup",
        display_name="DNS kaydı",
        description=(
            "Cloudflare DoH (cloudflare-dns.com) ile bir alan adının A/AAAA/MX/TXT/NS "
            "kaydını okur. Kabuk ve serbest resolver yok. "
            "Ne zaman: DNS, MX, NS, 'şu domain nereye gidiyor'. "
            "Ne zaman değil: IP konumu → ip_lookup; localhost/.local yok; "
            "sayfa oku → web_fetch."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca cloudflare-dns.com'a salt-okunur GET gider.",
        parameters=[
            _p("name", "Alan adı (example.com)", required=True),
            _p(
                "record_type",
                "Kayıt türü.",
                enum=["A", "AAAA", "MX", "TXT", "NS", "CNAME"],
                default="A",
            ),
        ],
    ),
    ToolDefinition(
        name="pollen",
        display_name="Polen",
        description=(
            "Open-Meteo CAMS ile bir yerin güncel polen (huş, çimen, zeytin…) "
            "yoğunluğunu okur. air_quality rewrite değildir. "
            "Ne zaman: polen, alerji, 'polen durumu'. "
            "Ne zaman değil: AQI/PM → air_quality; sıcaklık → weather."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Open-Meteo hava kalitesi API'sine GET gider.",
        parameters=[_p("place", "Şehir veya yer adı", required=True)],
    ),
    ToolDefinition(
        name="fx_rate",
        display_name="Döviz kuru",
        description=(
            "Frankfurter (api.frankfurter.dev) üzerinden resmi merkez bankası karışık kuru "
            "okur ve tutarı çevirir. Anahtar yok, kabuk yok, serbest URL yok. "
            "Ne zaman: USD/EUR/TRY vb. kur veya '100 dolar kaç TL'. "
            "Ne zaman değil: kripto → web_search; aritmetik/birim → calculate; "
            "tarihsel haber yorumu → web_news."
        ),
        category="web",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca Frankfurter'a salt-okunur bir GET gider.",
        parameters=[
            _p("base", "Kaynak ISO kodu (USD, EUR, TRY…)", required=True),
            _p("quote", "Hedef ISO kodu", required=True),
            _p("amount", "Çevrilecek tutar", type_="number", default=1),
        ],
    ),
    ToolDefinition(
        name="calculate",
        display_name="Hesapla / birim çevir",
        description=(
            "Yerel aritmetik ve birim çevirme. Kullanıcı toplam, çarpım, yüzde veya "
            "km↔mil, kg↔lb, °C↔°F, litre↔galon, km/sa↔m/s sorduğunda kullan. "
            "Kabuk, Python veya Windows hesap makinesi açmaz. "
            "Ne zaman değil: 'hesap makinesini aç' → open_application (calc); "
            "tarih/saat → prompt'taki İstanbul saati; döviz kuru → fx_rate; "
            "IBAN doğrula → iban_check; kripto fiyat → web_search; "
            "kod çalıştırma veya serbest ifade yok."
        ),
        category="system",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca yerel hesap yapılır; ağ ve kabuk yok.",
        parameters=[
            _p(
                "expression",
                "Aritmetik ifade: 2+2, (3*5)/2, sqrt(9), 1,5*4. Yalnız + - * / // % **.",
            ),
            _p("value", "Çevrilecek sayı", type_="number"),
            _p("from_unit", "Kaynak birim (km, mil, kg, lb, c, f, l, gal, km/h)"),
            _p("to_unit", "Hedef birim"),
        ],
    ),
    ToolDefinition(
        name="iban_check",
        display_name="IBAN doğrula",
        description=(
            "Yerel ISO 13616 IBAN doğrulama (MOD-97). Ağ, kabuk ve banka API yok. "
            "Ne zaman: IBAN doğru mu, havale numarası, TR IBAN. "
            "Ne zaman değil: döviz → fx_rate; hesap/birim → calculate; "
            "banka bakiyesi veya EFT gönderme yok."
        ),
        category="system",
        risk=LOW,
        execution=BACKEND,
        impact="Yalnızca yerel checksum; ağ ve kabuk yok.",
        parameters=[_p("iban", "IBAN (boşluklu olabilir)", required=True)],
    ),

    ToolDefinition(
        name="search_documents",
        display_name="Belgelerde ara",
        description=(
            "Uryx'e eklenmiş belgelerde anlamsal arama yapar. "
            "Ne zaman: kullanıcının yüklediği PDF/docx/not. "
            "Ne zaman değil: internet/Wikipedia → wiki_lookup veya web_search; "
            "kalıcı kişisel tercih → search_memory."
        ),
        category="rag",
        risk=LOW,
        execution=BACKEND,
        parameters=[
            _p("query", "Aranacak metin", required=True),
            _p("top_k", "Sonuç sayısı", type_="integer", default=5),
        ],
    ),
    ToolDefinition(
        name="search_memory",
        display_name="Hafızada ara",
        description="Kullanıcı hakkında daha önce kaydedilmiş kalıcı bilgilerde arama yapar.",
        category="memory",
        risk=LOW,
        execution=BACKEND,
        parameters=[
            _p("query", "Aranacak metin", required=True),
            _p("top_k", "Sonuç sayısı", type_="integer", default=5),
        ],
    ),
    ToolDefinition(
        name="save_memory",
        display_name="Hafızaya kaydet",
        description=(
            "Kullanıcının açıkça hatırlanmasını istediği bilgiyi kalıcı hafızaya yazar. "
            "Şifre, token veya API anahtarı ASLA kaydetme."
        ),
        category="memory",
        risk=MEDIUM,
        execution=BACKEND,
        impact="Bilgi kalıcı hafızaya eklenir ve sonraki sohbetlerde kullanılır.",
        parameters=[
            _p("content", "Kaydedilecek bilgi (tek cümle)", required=True),
            _p(
                "category",
                "Bilgi kategorisi",
                enum=[
                    "preference",
                    "system_info",
                    "project",
                    "folder",
                    "application",
                    "contact",
                    "fact",
                    "other",
                ],
                default="other",
            ),
        ],
    ),
    ToolDefinition(
        name="mcp_list_tools",
        display_name="MCP araçlarını listele",
        description=(
            "Kayıtlı bir MCP sunucusuna initialize + tools/list gönderir. "
            "Yalnızca kullanıcının allowlist'lediği araç adları çağrılabilir olarak döner. "
            "Önerilen kimlikler: fetch (sayfa markdown), time (saat dilimi), "
            "docs (kütüphane belgesi), think (adım adım düşünme). "
            "playwright / github / brave / huggingface / weather / wikipedia / arxiv / "
            "wikidata / youtube / hn / ddg / openlibrary / translate / rss / geocode: "
            "Ayarlar tarif kartı; native araç değil."
        ),
        category="mcp",
        risk=LOW,
        execution=HOST,
        parameters=[_p("server", "Ayarlardaki MCP sunucu kimliği", required=True)],
    ),
    ToolDefinition(
        name="mcp_call",
        display_name="MCP aracı çağır",
        description=(
            "Kullanıcının Ayarlar'da allowlist'lediği bir MCP sunucusundaki aracı çağırır. "
            "Sunucu komutu model tarafından seçilemez; yalnızca kayıtlı sunucu kimliği ve "
            "o sunucuya izin verilen araç adları kabul edilir. Kabuk veya rasgele süreç açmaz. "
            "fetch.fetch: URL'yi markdown olarak al (tarayıcı penceresi gerekmez). "
            "time.get_current_time / convert_time: IANA saat dilimi. "
            "docs.resolve-library-id sonra query-docs veya get-library-docs: kütüphane belgesi. "
            "think.sequential_thinking: çok adımlı plan. "
            "playwright (Ayarlar tarif kartı, varsayılan katalogda yok): "
            "browser_navigate + browser_snapshot — a11y ağacı; tıklama/yazma allowlist'te yok. "
            "github (Ayarlar tarif kartı, docker yok): npx @modelcontextprotocol/server-github; "
            "salt okuma (arama/dosya/issue/PR). Yazma JSON'a eklenirse yine onay. "
            "brave: Brave Search API (web/haber/yerel); huggingface: Hub arama/belge "
            "(hf_jobs yok); weather: Open-Meteo (uvx); wikipedia: madde özeti; "
            "arxiv: arama/özet/atıf (indirme yok); wikidata: varlık/SPARQL; "
            "youtube: altyazı; hn: Hacker News; ddg: DuckDuckGo arama (fetch yok); "
            "openlibrary: kitap/ISBN; translate: LibreTranslate; rss: get_feed; "
            "geocode: OSM Nominatim (ham Overpass yok). "
            "Etkileşimli gezinme için browser_open / browser_read_page veya mcp_call onayı. "
            "Dosya, git, bellek ve serbest tarayıcı için yerleşik Uryx araçlarını kullan; "
            "MCP filesystem/git/memory açma. Yerel git için git_status."
        ),
        category="mcp",
        risk=HIGH,
        execution=HOST,
        impact="Yerel MCP sunucusuna allowlist'li bir araç çağrısı gider.",
        parameters=[
            _p("server", "Ayarlardaki MCP sunucu kimliği", required=True),
            _p("tool", "Sunucuda izin verilen araç adı", required=True),
            _p(
                "arguments",
                "Araca JSON nesnesi olarak geçirilecek argümanlar",
                type_="object",
                default={},
            ),
        ],
    ),
]

_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}

class ToolRegistry:
    """Araç tanımlarını tutar, doğrular ve LLM şemasına çevirir."""

    def __init__(self, definitions: list[ToolDefinition] | None = None) -> None:

        self._tools: dict[str, ToolDefinition] = {
            tool.name: tool.model_copy(deep=True) for tool in (definitions or TOOL_DEFINITIONS)
        }

    def get(self, name: str) -> ToolDefinition:
        """Araç tanımını döndürür.

        Raises:
            ToolNotAllowedError: Araç allowlist'te yoksa veya kapalıysa.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotAllowedError(
                loc(
                    f"'{name}' adında bir araç yok veya izin listesinde değil.",
                    f"There is no tool named '{name}', or it is not on the allowlist.",
                ),
                details={"available": sorted(self._tools)},
            )
        if not tool.enabled:
            raise ToolNotAllowedError(
                loc(f"'{name}' aracı devre dışı bırakılmış.", f"The '{name}' tool is disabled.")
            )
        return localize_tool(tool)

    def has(self, name: str) -> bool:
        """Araç kayıtlı mı?"""
        return name in self._tools

    def all(self) -> list[ToolDefinition]:
        """Tüm araç tanımları (ada göre sıralı)."""
        return sorted(
            (localize_tool(tool) for tool in self._tools.values()),
            key=lambda t: (t.category, t.name),
        )

    def enabled(self) -> list[ToolDefinition]:
        """Etkin araçlar."""
        return [t for t in self.all() if t.enabled]

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Aracı etkinleştirir/devre dışı bırakır."""
        if name in self._tools:
            self._tools[name].enabled = enabled

    def openai_schemas(self, *, categories: set[str] | None = None) -> list[dict[str, Any]]:
        """vLLM'e gönderilecek tool şemaları."""
        return [
            tool.to_openai_schema()
            for tool in self.enabled()
            if categories is None or tool.category in categories
        ]

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Argümanları tanıma göre doğrular ve normalize eder.

        Bilinmeyen argümanlar sessizce atılır (model bazen fazladan alan üretir);
        zorunlu alan eksikse veya tip uyuşmuyorsa hata verilir.

        Raises:
            ValidationError: Argümanlar tanıma uymuyorsa.
        """
        tool = self.get(name)
        required = [p.name for p in tool.parameters if p.required]
        if not isinstance(arguments, dict):
            raise ValidationError(
                f"'{name}' için argümanlar bir nesne olmalı.",
                details={"required": required, "received": []},
            )

        known = {p.name: p for p in tool.parameters}
        remapped = _remap_argument_keys(known, arguments)
        cleaned: dict[str, Any] = {}

        for key, value in remapped.items():
            param = known.get(key)
            if param is None:
                continue
            try:
                cleaned[key] = _coerce(name, param.name, param.type, value)
            except ValidationError as exc:
                raise ValidationError(
                    exc.user_message,
                    details={
                        "required": required,
                        "received": sorted(remapped),
                        "field": param.name,
                    },
                ) from exc
            if param.enum and str(cleaned[key]) not in param.enum:
                raise ValidationError(
                    f"'{name}.{param.name}' değeri şunlardan biri olmalı: {', '.join(param.enum)}",
                    details={
                        "required": required,
                        "received": sorted(remapped),
                        "field": param.name,
                    },
                )

        for param in tool.parameters:
            if param.name in cleaned:
                continue
            if param.required:
                raise ValidationError(
                    f"'{name}' aracı için '{param.name}' parametresi zorunlu.",
                    details={
                        "required": required,
                        "received": sorted(cleaned),
                        "missing": param.name,
                    },
                )
            if param.default is not None:
                cleaned[param.name] = param.default

        return cleaned

    def requires_confirmation(self, name: str, *, confirmation_enabled: bool = True) -> bool:
        """Araç kullanıcı onayı gerektiriyor mu?"""
        tool = self.get(name)
        if tool.risk is RiskLevel.LOW:
            return False

        if tool.risk is RiskLevel.HIGH:
            return True
        return confirmation_enabled

_ARG_KEY_ALIASES = {
    "commands": "command",
    "cmd": "command",
    "q": "query",
    "search": "query",
    "search_query": "query",
}

def _remap_argument_keys(known: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """OpenHands gemma ``commands``→``command``: yalnız hedef alan varken."""
    remapped: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in known:
            remapped.setdefault(key, value)
            continue
        target = _ARG_KEY_ALIASES.get(key)
        if target and target in known and target not in arguments and target not in remapped:
            remapped[target] = value
    return remapped

def _coerce(tool: str, field: str, expected: str, value: Any) -> Any:
    """Değeri beklenen tipe dönüştürür (LLM string üretme eğilimindedir)."""
    types = _TYPE_MAP.get(expected, (str,))
    if isinstance(value, types) and not (expected != "boolean" and isinstance(value, bool)):
        return value

    try:
        if expected == "integer":
            return int(str(value).strip())
        if expected == "number":
            return float(str(value).strip())
        if expected == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"true", "1", "yes", "evet", "on"}
        if expected == "string":
            if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                return "".join(value)
            if isinstance(value, dict | list):
                raise ValueError("karmaşık tip")
            return str(value)
        if expected == "array" and isinstance(value, str):
            stripped = value.strip()
            if stripped[:1] == "[":
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return parsed
            return [v.strip() for v in value.split(",") if v.strip()]
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"'{tool}.{field}' parametresi {expected} tipinde olmalı.") from exc

    raise ValidationError(f"'{tool}.{field}' parametresi {expected} tipinde olmalı.")
