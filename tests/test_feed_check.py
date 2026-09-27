"""Tests de core/feed_check.py (Catégorie F : veille RSS/Atom)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from core.feed_check import check_feed, parse_feed_items

RSS_SAMPLE_V1 = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Mon blog</title>
<item><guid>id-1</guid><title>Premier article</title><link>https://exemple.test/1</link></item>
<item><guid>id-2</guid><title>Deuxième article</title><link>https://exemple.test/2</link></item>
</channel>
</rss>
"""

RSS_SAMPLE_V2 = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Mon blog</title>
<item><guid>id-3</guid><title>Troisième article (nouveau)</title><link>https://exemple.test/3</link></item>
<item><guid>id-2</guid><title>Deuxième article</title><link>https://exemple.test/2</link></item>
<item><guid>id-1</guid><title>Premier article</title><link>https://exemple.test/1</link></item>
</channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Mon blog Atom</title>
<entry>
<id>atom-1</id>
<title>Entrée Atom</title>
<link href="https://exemple.test/atom-1"/>
</entry>
</feed>
"""


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def _client(xml_text: str, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=xml_text)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_parse_feed_items_rss20():
    items = parse_feed_items(RSS_SAMPLE_V1)
    assert len(items) == 2
    assert items[0]["id"] == "id-1"
    assert items[0]["title"] == "Premier article"
    assert items[0]["link"] == "https://exemple.test/1"


def test_parse_feed_items_atom():
    items = parse_feed_items(ATOM_SAMPLE)
    assert len(items) == 1
    assert items[0]["id"] == "atom-1"
    assert items[0]["link"] == "https://exemple.test/atom-1"


def test_parse_feed_items_invalid_xml_returns_empty_list():
    assert parse_feed_items("<not><valid") == []


def test_parse_feed_items_empty_feed_returns_empty_list():
    assert parse_feed_items("<rss><channel></channel></rss>") == []


def test_missing_url_raises_value_error():
    with pytest.raises(ValueError):
        asyncio.run(check_feed(url=""))


def test_first_check_seeds_state_without_notifying():
    from core.notifications import list_notifications

    result = asyncio.run(check_feed("https://exemple.test/feed", client=_client(RSS_SAMPLE_V1)))

    assert result["items_total"] == 2
    assert result["new_items"] == 0
    assert list_notifications() == []  # jamais de spam au premier contrôle


def test_second_check_notifies_only_the_truly_new_item():
    from core.notifications import list_notifications

    asyncio.run(check_feed("https://exemple.test/feed", name="Mon blog", client=_client(RSS_SAMPLE_V1)))
    result = asyncio.run(
        check_feed("https://exemple.test/feed", name="Mon blog", client=_client(RSS_SAMPLE_V2))
    )

    assert result["new_items"] == 1
    notifs = list_notifications()
    assert len(notifs) == 1
    assert "Troisième article" in notifs[0]["message"]
    assert "Mon blog" in notifs[0]["message"]


def test_unchanged_feed_never_renotifies_known_items():
    from core.notifications import list_notifications

    asyncio.run(check_feed("https://exemple.test/feed", client=_client(RSS_SAMPLE_V1)))
    asyncio.run(check_feed("https://exemple.test/feed", client=_client(RSS_SAMPLE_V1)))
    asyncio.run(check_feed("https://exemple.test/feed", client=_client(RSS_SAMPLE_V1)))

    assert list_notifications() == []


def test_http_error_propagates():
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(check_feed("https://exemple.test/feed", client=_client("", status_code=500)))
