"""Sohbet oturumu: durdurunca onay bileti ve bekleyen future."""

from __future__ import annotations

import asyncio

import pytest
from app.api.ws.chat import ChatSession
from app.services.tools.policy import ConfirmationTicketStore

class _DummyWs:
    pass

@pytest.mark.asyncio
async def test_cancel_turn_mcp_onay_biletini_yakar() -> None:
    session = ChatSession(_DummyWs())  # type: ignore[arg-type]
    future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
    session.pending_confirmations["req-mcp"] = future
    tickets = ConfirmationTicketStore()
    ticket = tickets.issue("mcp_call", "fp-docs")
    session.pending_tickets["req-mcp"] = ticket

    session.cancel_turn(revoke_ticket=tickets.revoke)

    assert future.done()
    decision = future.result()
    assert decision.approved is False
    assert decision.reason == "cancelled"
    assert tickets.consume(ticket, "mcp_call", "fp-docs") is False

@pytest.mark.asyncio
async def test_ikinci_onay_cevabi_ilki_kazanir() -> None:
    session = ChatSession(_DummyWs())  # type: ignore[arg-type]
    future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
    session.pending_confirmations["req-1"] = future
    session.resolve_confirmation("req-1", True, fingerprint="fp-a")
    session.resolve_confirmation("req-1", False, fingerprint="fp-b")
    decision = future.result()
    assert decision.approved is True
    assert decision.fingerprint == "fp-a"
    session.resolve_confirmation("missing", True)

@pytest.mark.asyncio
async def test_cancel_turn_bilet_olmadan_future_iptal() -> None:
    session = ChatSession(_DummyWs())  # type: ignore[arg-type]
    future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
    session.pending_confirmations["req-2"] = future
    session.cancel_turn()
    assert future.result().reason == "cancelled"
