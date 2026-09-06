"""Barge-in: söylenmemiş TTS kuyruğu yayınlanmaz / persist edilmez."""

from __future__ import annotations

import asyncio
from typing import Any

def spoken_assistant_content(full: str, spoken: str) -> str:
    heard = (spoken or "").strip()
    if not heard:
        return ""
    text = (full or "").strip()
    if text.startswith(heard):
        return heard
    return heard

def drain_tts_queue(queue: asyncio.Queue[Any]) -> int:
    """Kalan cümleleri emit etmeden düşür. ``None`` sentinel sayılmaz."""
    dropped = 0
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is not None:
            dropped += 1
        queue.task_done()
    return dropped
