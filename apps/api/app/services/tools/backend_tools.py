"""Backend (container) içinde çalışan araç implementasyonları.

Docker araçları ``/var/run/docker.sock`` üzerinden çalışır; soket bağlı değilse
araçlar anlaşılır bir hata döndürür.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from app.core.errors import ToolExecutionError
from app.core.locale import ui_language
from app.core.logging import get_logger
from app.db.models import MemoryCategory
from app.services.tools.policy import (
    MAX_TRANSIENT_RETRIES,
    is_idempotent,
    retry_backoff_seconds,
    retry_exhausted_message,
    should_retry_transient,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.memory.service import MemoryService
from app.services.rag.service import RAGService
from app.services.tools.calc import run_calculate
from app.services.tools.iban import run_iban_check
from app.services.web.air_quality import lookup_air_quality
from app.services.web.countries import lookup_country
from app.services.web.dictionary import lookup_dictionary
from app.services.web.dns import lookup_dns
from app.services.web.doi import lookup_doi
from app.services.web.earthquakes import lookup_earthquakes
from app.services.web.elevation import lookup_elevation
from app.services.web.fetch import fetch_public_page
from app.services.web.food import lookup_food_barcode
from app.services.web.fx import lookup_fx_rate
from app.services.web.ipgeo import lookup_ip
from app.services.web.iss import lookup_iss_now
from app.services.web.holidays import lookup_public_holidays
from app.services.web.npm import lookup_npm
from app.services.web.pollen import lookup_pollen
from app.services.web.postal import lookup_postal
from app.services.web.prayer import lookup_prayer_times
from app.services.web.pypi import lookup_pypi
from app.services.web.search import WebSearchService
from app.services.web.space_weather import lookup_space_weather
from app.services.web.sun import lookup_sun_times
from app.services.web.weather import lookup_weather
from app.services.web.wiki import lookup_wikipedia

logger = get_logger(__name__)

ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]

MANAGED_CONTAINER_PREFIX = "uryx-"

class DockerToolset:
    """Docker konteyner araçları."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._checked = False

    def _get_client(self) -> Any:
        """Docker istemcisini tembel yükler."""
        if self._client is not None:
            return self._client
        try:
            import docker

            self._client = docker.from_env()
            self._client.ping()
        except Exception as exc:
            raise ToolExecutionError(
                "Docker soketine erişilemiyor. uryx-api konteyneri "
                "/var/run/docker.sock bağlamıyla çalıştırılmalı.",
                details={"error": str(exc)},
            ) from exc
        return self._client

    def _resolve(self, name: str) -> Any:
        """Konteyneri bulur ve Uryx'e ait olduğunu doğrular."""
        client = self._get_client()
        try:
            container = client.containers.get(name)
        except Exception as exc:
            raise ToolExecutionError(f"'{name}' adlı konteyner bulunamadı.") from exc

        if not str(container.name).startswith(MANAGED_CONTAINER_PREFIX):
            raise ToolExecutionError(
                f"'{container.name}' Uryx tarafından yönetilmiyor. "
                f"Yalnızca '{MANAGED_CONTAINER_PREFIX}*' konteynerleri üzerinde işlem yapılabilir."
            )
        return container

    async def list_containers(self, args: dict[str, Any]) -> dict[str, Any]:
        """Konteynerleri listeler."""
        show_all = bool(args.get("all", True))

        def _run() -> dict[str, Any]:
            client = self._get_client()
            containers = client.containers.list(all=show_all)
            return {
                "containers": [
                    {
                        "name": c.name,
                        "status": c.status,
                        "image": (c.image.tags or ["<none>"])[0] if c.image else "<none>",
                        "managed": str(c.name).startswith(MANAGED_CONTAINER_PREFIX),
                        "health": (c.attrs.get("State", {}).get("Health", {}) or {}).get("Status"),
                    }
                    for c in containers
                ]
            }

        return await asyncio.to_thread(_run)

    async def start_container(self, args: dict[str, Any]) -> dict[str, Any]:
        """Konteyneri başlatır."""
        name = str(args["name"])

        def _run() -> dict[str, Any]:
            container = self._resolve(name)
            container.start()
            container.reload()
            return {"name": container.name, "status": container.status, "started": True}

        return await asyncio.to_thread(_run)

    async def stop_container(self, args: dict[str, Any]) -> dict[str, Any]:
        """Konteyneri durdurur."""
        name = str(args["name"])

        def _run() -> dict[str, Any]:
            container = self._resolve(name)
            container.stop(timeout=20)
            container.reload()
            return {"name": container.name, "status": container.status, "stopped": True}

        return await asyncio.to_thread(_run)

    async def remove_container(self, args: dict[str, Any]) -> dict[str, Any]:
        """Durdurulmuş konteyneri siler."""
        name = str(args["name"])

        def _run() -> dict[str, Any]:
            container = self._resolve(name)
            if container.status == "running":
                raise ToolExecutionError(f"'{container.name}' çalışıyor. Önce durdurulmalı.")
            container_name = container.name
            container.remove(v=False)
            return {"name": container_name, "removed": True}

        return await asyncio.to_thread(_run)

    async def container_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        """Konteyner loglarını getirir."""
        name = str(args["name"])
        lines = max(1, min(int(args.get("lines", 50)), 500))

        def _run() -> dict[str, Any]:
            container = self._resolve(name)
            raw = container.logs(tail=lines, timestamps=False)
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            return {"name": container.name, "lines": text.splitlines()[-lines:]}

        return await asyncio.to_thread(_run)

class BackendToolset:
    """Container içinde çalışan tüm araçların yönlendiricisi."""

    def __init__(
        self,
        rag_service: RAGService,
        memory_service: MemoryService,
        web_search: WebSearchService | None = None,
    ) -> None:
        self._docker = DockerToolset()
        self._rag = rag_service
        self._memory = memory_service
        self._web_search = web_search or WebSearchService()
        self._handlers: dict[str, ToolHandler] = {
            "docker_list_containers": self._docker.list_containers,
            "docker_start_container": self._docker.start_container,
            "docker_stop_container": self._docker.stop_container,
            "docker_remove_container": self._docker.remove_container,
            "docker_container_logs": self._docker.container_logs,
            "search_documents": self._search_documents,
            "search_memory": self._search_memory,
            "save_memory": self._save_memory,
            "web_search": self._search_web,
            "web_research": self._research_web,
            "web_social_profile": self._resolve_social_profile,
            "web_image_search": self._search_web_images,
            "web_video_search": self._search_web_videos,
            "web_news": self._search_web_news,
            "web_fetch": self._fetch_web_page,
            "wiki_lookup": self._lookup_wiki,
            "dict_lookup": self._lookup_dict,
            "fx_rate": self._lookup_fx,
            "weather": self._lookup_weather,
            "public_holidays": self._lookup_holidays,
            "air_quality": self._lookup_air_quality,
            "earthquakes": self._lookup_earthquakes,
            "country_info": self._lookup_country,
            "prayer_times": self._lookup_prayer,
            "sun_times": self._lookup_sun,
            "postal_lookup": self._lookup_postal,
            "iss_now": self._lookup_iss,
            "space_weather": self._lookup_space_weather,
            "doi_lookup": self._lookup_doi,
            "elevation": self._lookup_elevation,
            "pypi_lookup": self._lookup_pypi,
            "ip_lookup": self._lookup_ip,
            "food_barcode": self._lookup_food,
            "npm_lookup": self._lookup_npm,
            "dns_lookup": self._lookup_dns,
            "pollen": self._lookup_pollen,
            "calculate": self._calculate,
            "iban_check": self._check_iban,
        }

    def supports(self, tool_name: str) -> bool:
        """Bu araç backend'de mi çalışıyor?"""
        return tool_name in self._handlers

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Aracı çalıştırır; salt-okunur araçlarda geçici hataları tekrar dener."""
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ToolExecutionError(f"'{tool_name}' backend tarafında tanımlı değil.")
        last_error: Exception | None = None
        attempts = MAX_TRANSIENT_RETRIES if is_idempotent(tool_name) else 1
        for attempt in range(attempts):
            try:
                return await handler(arguments)
            except ToolExecutionError:
                raise
            except (OSError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if not should_retry_transient(
                    tool_name=tool_name,
                    attempt=attempt,
                    retryable=True,
                    timed_out=isinstance(exc, TimeoutError),
                ):
                    break
                delay = retry_backoff_seconds(attempt)
                logger.info(
                    "backend_tool_retry",
                    tool=tool_name,
                    attempt=attempt + 1,
                    delay_s=delay,
                    error=str(exc)[:200],
                )
                await asyncio.sleep(delay)
        used = attempt + 1
        raise ToolExecutionError(
            retry_exhausted_message(
                f"'{tool_name}' geçici bir altyapı hatası verdi.",
                used,
            ),
            details={
                "error": str(last_error) if last_error else "unknown",
                "retries": used,
            },
        ) from last_error

    async def _search_web(self, args: dict[str, Any]) -> dict[str, Any]:
        """İnternette güncel bilgi arar (bölge / site / dosya türü)."""
        query = str(args["query"])
        region = str(args.get("region") or "tr-tr")
        timelimit = str(args.get("timelimit") or "") or None
        site = str(args.get("site") or "").strip()
        filetype = str(args.get("filetype") or "").strip()
        exclude_site = str(args.get("exclude_site") or "").strip()
        results = await self._web_search.search(
            query,
            max_results=int(args.get("max_results", 5)),
            region=region,
            timelimit=timelimit,
            site=site,
            filetype=filetype,
            exclude_site=exclude_site,
        )
        return {
            "query": query,
            "count": len(results),
            "region": region,
            "timelimit": timelimit,
            "site": site or None,
            "exclude_site": exclude_site or None,
            "filetype": filetype or None,
            "results": results,
        }

    async def _research_web(self, args: dict[str, Any]) -> dict[str, Any]:
        """Çok sorgulu, tekilleştirilmiş güncel kanıt seti toplar."""
        results = await self._web_search.research(
            str(args["query"]), max_results=int(args.get("max_results", 10))
        )
        domains = sorted({str(result.get("domain") or "") for result in results if result})
        return {
            "query": str(args["query"]),
            "count": len(results),
            "source_count": len([domain for domain in domains if domain]),
            "domains": domains,
            "results": results,
        }

    async def _search_web_images(self, args: dict[str, Any]) -> dict[str, Any]:
        """İnternette görsel arar; sonuçlar masaüstünde galeri olarak gösterilir."""
        images = await self._web_search.image_search(
            str(args["query"]), max_results=int(args.get("max_results", 6))
        )
        verified_count = sum(int(image.get("platform_verified", 0)) for image in images)
        return {
            "query": str(args["query"]),
            "count": len(images),
            "verified_count": verified_count,
            "images": images,
        }

    async def _resolve_social_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        """Resmi Instagram hesabını ve indekslenen en yeni gönderiyi doğrular."""
        return await self._web_search.social_profile(str(args["query"]))

    async def _search_web_videos(self, args: dict[str, Any]) -> dict[str, Any]:
        """Video sonuçlarını merkez medya paneli için yapılandırılmış olarak döndürür."""
        videos = await self._web_search.video_search(
            str(args["query"]), max_results=int(args.get("max_results", 6))
        )
        return {"query": str(args["query"]), "count": len(videos), "videos": videos}

    async def _search_web_news(self, args: dict[str, Any]) -> dict[str, Any]:
        """Haber dizininde arar (tarih + kaynak + bölge)."""
        query = str(args["query"])
        timelimit = str(args.get("timelimit") or "w")
        region = str(args.get("region") or "tr-tr")
        safesearch = str(args.get("safesearch") or "moderate")
        source = str(args.get("source") or "").strip()
        results = await self._web_search.news(
            query,
            max_results=int(args.get("max_results", 8)),
            timelimit=timelimit,
            region=region,
            safesearch=safesearch,
            source=source,
        )
        return {
            "query": query,
            "count": len(results),
            "region": region,
            "timelimit": timelimit,
            "safesearch": safesearch,
            "source": source or None,
            "results": results,
        }

    async def _calculate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Aritmetik ve birim çevirme; kabuk yok."""
        return await asyncio.to_thread(run_calculate, args)

    async def _check_iban(self, args: dict[str, Any]) -> dict[str, Any]:
        """Yerel IBAN MOD-97; ağ yok."""
        return await asyncio.to_thread(run_iban_check, args)

    async def _lookup_wiki(self, args: dict[str, Any]) -> dict[str, Any]:
        """Wikimedia REST özet; yalnız wikipedia.org."""
        return await lookup_wikipedia(
            str(args["title"]), lang=str(args.get("lang") or ui_language())
        )

    async def _lookup_dict(self, args: dict[str, Any]) -> dict[str, Any]:
        """Wiktionary tanım; yalnız wiktionary.org."""
        return await lookup_dictionary(
            str(args["term"]), lang=str(args.get("lang") or ui_language())
        )

    async def _lookup_earthquakes(self, args: dict[str, Any]) -> dict[str, Any]:
        """USGS deprem; yalnız earthquake.usgs.gov."""
        mag = args.get("minmagnitude")
        days = args.get("days")
        return await lookup_earthquakes(
            region=str(args.get("region") or "tr"),
            minmagnitude=float(mag) if mag not in (None, "") else None,
            days=int(days) if days not in (None, "") else None,
        )

    async def _lookup_country(self, args: dict[str, Any]) -> dict[str, Any]:
        """REST Countries; yalnız restcountries.com."""
        return await lookup_country(str(args["query"]))

    async def _lookup_prayer(self, args: dict[str, Any]) -> dict[str, Any]:
        """Aladhan namaz; yalnız api.aladhan.com."""
        method = args.get("method")
        return await lookup_prayer_times(
            str(args["city"]),
            country=str(args.get("country") or "TR"),
            method=int(method) if method not in (None, "") else 13,
            date=str(args["date"]) if args.get("date") else None,
        )

    async def _lookup_sun(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open-Meteo gün doğumu/UV; weather rewrite yok."""
        days = args.get("days")
        return await lookup_sun_times(
            str(args["place"]),
            days=int(days) if days not in (None, "") else 1,
        )

    async def _lookup_postal(self, args: dict[str, Any]) -> dict[str, Any]:
        """Zippopotam posta kodu; yalnız api.zippopotam.us."""
        return await lookup_postal(
            str(args["code"]),
            country=str(args.get("country") or "TR"),
        )

    async def _lookup_iss(self, args: dict[str, Any]) -> dict[str, Any]:
        """ISS konumu; yalnız api.wheretheiss.at."""
        return await lookup_iss_now()

    async def _lookup_space_weather(self, args: dict[str, Any]) -> dict[str, Any]:
        """NOAA SWPC ölçekleri; yalnız services.swpc.noaa.gov."""
        return await lookup_space_weather()

    async def _lookup_doi(self, args: dict[str, Any]) -> dict[str, Any]:
        """Crossref DOI; yalnız api.crossref.org."""
        return await lookup_doi(str(args["doi"]))

    async def _lookup_elevation(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open-Meteo rakım; weather rewrite yok."""
        return await lookup_elevation(str(args["place"]))

    async def _lookup_pypi(self, args: dict[str, Any]) -> dict[str, Any]:
        """PyPI paket; yalnız pypi.org."""
        return await lookup_pypi(str(args["name"]))

    async def _lookup_ip(self, args: dict[str, Any]) -> dict[str, Any]:
        """ipwho.is genel IP; özel ağ yok."""
        return await lookup_ip(str(args["ip"]))

    async def _lookup_food(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open Food Facts barkod; yalnız world.openfoodfacts.org."""
        return await lookup_food_barcode(str(args["barcode"]))

    async def _lookup_npm(self, args: dict[str, Any]) -> dict[str, Any]:
        """npm registry; yalnız registry.npmjs.org."""
        return await lookup_npm(str(args["name"]))

    async def _lookup_dns(self, args: dict[str, Any]) -> dict[str, Any]:
        """Cloudflare DoH; yalnız cloudflare-dns.com."""
        return await lookup_dns(
            str(args["name"]),
            record_type=str(args.get("record_type") or "A"),
        )

    async def _lookup_pollen(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open-Meteo polen; air_quality rewrite yok."""
        return await lookup_pollen(str(args["place"]))

    async def _lookup_fx(self, args: dict[str, Any]) -> dict[str, Any]:
        """Frankfurter kur; yalnız api.frankfurter.dev."""
        return await lookup_fx_rate(
            base=str(args["base"]),
            quote=str(args["quote"]),
            amount=float(args.get("amount") or 1),
        )

    async def _lookup_weather(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open-Meteo; yalnız open-meteo hostları."""
        return await lookup_weather(
            str(args["place"]), days=int(args.get("days") or 3)
        )

    async def _lookup_air_quality(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open-Meteo AQI; yalnız air-quality-api.open-meteo.com."""
        return await lookup_air_quality(str(args["place"]))

    async def _lookup_holidays(self, args: dict[str, Any]) -> dict[str, Any]:
        """Nager.Date resmi tatil; yalnız date.nager.at."""
        year = args.get("year")
        return await lookup_public_holidays(
            country=str(args.get("country") or "TR"),
            year=int(year) if year not in (None, "") else None,
        )

    async def _fetch_web_page(self, args: dict[str, Any]) -> dict[str, Any]:
        """Oturumsuz, SSRF-korumalı sayfa metni."""
        return await fetch_public_page(
            str(args["url"]),
            max_chars=int(args.get("max_chars", 8000)),
            start_index=int(args.get("start_index", 0)),
        )

    async def _search_documents(self, args: dict[str, Any]) -> dict[str, Any]:
        """Belgelerde anlamsal arama."""
        hits = await self._rag.search(
            str(args["query"]), top_k=max(1, min(int(args.get("top_k", 5)), 20))
        )
        return {
            "count": len(hits),
            "results": [
                {
                    "chunk_id": h.chunk_id,
                    "document_id": h.document_id,
                    "filename": h.filename,
                    "page": h.page,
                    "score": round(h.score, 3),
                    "content": h.content[:800],
                }
                for h in hits
            ],
        }

    async def _search_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        """Kalıcı hafızada arama."""
        refs = await self._memory.search(
            str(args["query"]), top_k=max(1, min(int(args.get("top_k", 5)), 20))
        )
        return {
            "count": len(refs),
            "results": [
                {"content": r.content, "category": r.category, "score": r.score} for r in refs
            ],
        }

    async def _save_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        """Kalıcı hafızaya yazar (hassas veri filtresinden geçirerek)."""
        from app.services.memory.evaluator import MemoryEvaluator

        content = str(args["content"]).strip()
        if MemoryEvaluator.contains_sensitive(content):
            raise ToolExecutionError(
                "Bu bilgi hassas veri (şifre/token/anahtar) içerdiği için kaydedilmedi."
            )
        if MemoryEvaluator.is_self_referential(content):
            raise ToolExecutionError(
                "Hafızaya kendi kayıt eylemini değil, kullanıcıya ait kalıcı bilgiyi yaz."
            )
        try:
            category = MemoryCategory(str(args.get("category", "other")).lower())
        except ValueError:
            category = MemoryCategory.OTHER

        memory = await self._memory.create(
            content, category=category, importance=0.75, source="manual"
        )
        return {
            "saved": True,
            "memory_id": memory.id,
            "content": content,
            "category": category.value,
        }
