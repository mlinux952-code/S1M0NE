"""Tests de core/url_check.py (Catégorie F : surveillance de disponibilité d'URL)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from core.url_check import check_url


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def _client(status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _raising_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connexion refusée", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_missing_url_raises_value_error():
    with pytest.raises(ValueError):
        asyncio.run(check_url(url=""))


def test_first_check_never_notifies_even_if_up():
    from core.notifications import list_notifications

    result = asyncio.run(check_url("https://exemple.test", client=_client(200)))

    assert result["up"] is True
    assert result["status_code"] == 200
    assert result["state_changed"] is False
    assert list_notifications() == []


def test_repeated_success_does_not_spam_notifications():
    from core.notifications import list_notifications

    asyncio.run(check_url("https://exemple.test", client=_client(200)))
    asyncio.run(check_url("https://exemple.test", client=_client(200)))
    asyncio.run(check_url("https://exemple.test", client=_client(200)))

    assert list_notifications() == []


def test_transition_to_down_then_back_up_notifies_both_times():
    from core.notifications import list_notifications

    asyncio.run(check_url("https://exemple.test", client=_client(200)))  # état initial : up
    down_result = asyncio.run(check_url("https://exemple.test", client=_client(500)))  # bascule
    up_result = asyncio.run(check_url("https://exemple.test", client=_client(200)))  # remonte

    assert down_result["up"] is False
    assert down_result["state_changed"] is True
    assert up_result["up"] is True
    assert up_result["state_changed"] is True

    notifs = list_notifications()
    assert len(notifs) == 2
    assert notifs[0]["level"] == "success"  # le plus récent en premier (list_notifications)
    assert notifs[1]["level"] == "error"


def test_network_error_counts_as_down_with_error_detail():
    result = asyncio.run(check_url("https://exemple.test", client=_raising_client()))

    assert result["up"] is False
    assert result["status_code"] is None
    assert result["error"] is not None


def test_two_different_urls_are_tracked_independently():
    from core.notifications import list_notifications

    asyncio.run(check_url("https://a.test", client=_client(200)))
    asyncio.run(check_url("https://b.test", client=_client(200)))
    asyncio.run(check_url("https://a.test", client=_client(500)))  # seul 'a' bascule

    notifs = list_notifications()
    assert len(notifs) == 1
    assert "a.test" in notifs[0]["message"]
