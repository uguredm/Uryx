"""Faz 3.3 barge-in: söylenmemiş TTS persist edilmez."""

from __future__ import annotations

import asyncio

from app.services.chat.barge_in import drain_tts_queue, spoken_assistant_content

def test_spoken_assistant_content_keser() -> None:
    assert spoken_assistant_content("Merhaba dünya. Nasılsın?", "Merhaba dünya.") == "Merhaba dünya."
    assert spoken_assistant_content("Merhaba dünya.", "") == ""
    assert spoken_assistant_content("Merhaba dünya.", "Merhaba") == "Merhaba"

async def test_tts_kuyrugu_iptalde_kalan_cumleyi_yaymaz() -> None:
    queue: asyncio.Queue[tuple[str, int] | None] = asyncio.Queue()
    await queue.put(("Merhaba.", 0))
    await queue.put(("Söylenmeyecek.", 1))
    await queue.put(None)
    dropped = drain_tts_queue(queue)
    assert dropped == 2
    assert queue.empty()
