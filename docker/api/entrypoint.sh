#!/usr/bin/env bash
# ============================================================
#  uryx-api entrypoint
#   1) Docker soketi izinlerini hizala (docker araçları için)
#   2) PostgreSQL'i bekle
#   3) Alembic migration'larını uygula
#   4) Uygulamayı başlat
# ============================================================
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*" >&2; }

# --- 1) Docker soketi -------------------------------------------------
if [ -S /var/run/docker.sock ]; then
    SOCK_GID="$(stat -c '%g' /var/run/docker.sock)"
    if ! getent group "${SOCK_GID}" >/dev/null 2>&1; then
        groupadd -g "${SOCK_GID}" dockerhost 2>/dev/null || true
    fi
    SOCK_GROUP="$(getent group "${SOCK_GID}" | cut -d: -f1)"
    usermod -aG "${SOCK_GROUP}" jarvis 2>/dev/null || true
    log "docker.sock grubu hizalandı (gid=${SOCK_GID})"
else
    log "docker.sock bulunamadı — Docker araçları devre dışı kalacak"
fi

# --- 2) PostgreSQL bekle ----------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
    log "PostgreSQL bekleniyor..."
    python - <<'PY' || log "PostgreSQL'e ulaşılamadı; uygulama degraded modda başlayacak"
import asyncio, os, sys, re

url = os.environ.get("DATABASE_URL", "")
m = re.search(r"@([^:/]+):(\d+)/", url)
if not m:
    sys.exit(0)
host, port = m.group(1), int(m.group(2))

async def wait():
    for attempt in range(60):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            print(f"[entrypoint] PostgreSQL hazır ({host}:{port})")
            return 0
        except Exception:
            await asyncio.sleep(1)
    return 1

sys.exit(asyncio.run(wait()))
PY
fi

# --- 3) Migration -----------------------------------------------------
if [ -f /app/alembic.ini ]; then
    log "Alembic migration'ları uygulanıyor..."
    alembic upgrade head || log "UYARI: migration başarısız — uygulama yine de başlatılıyor"
fi

# --- 4) Başlat --------------------------------------------------------
log "Uygulama başlatılıyor: $*"
exec gosu jarvis "$@" 2>/dev/null || exec "$@"
