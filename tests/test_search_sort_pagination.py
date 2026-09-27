"""Tests de connectors/engine.py : sort_results / paginate_results (NEXT_STEPS.md §C.2)."""

from __future__ import annotations

import pytest

from connectors.engine import DEFAULT_PAGE_SIZE, SORT_OPTIONS, paginate_results, sort_results


def _r(name, source="github", **extra):
    return {"source": source, "name": name, "description": "", "url": "", "extra": extra}


# --- sort_results ----------------------------------------------------------------------------


def test_sort_options_are_exactly_expected():
    assert SORT_OPTIONS == ("relevance", "stars", "downloads", "name")


def test_sort_relevance_preserves_original_order():
    results = [_r("c"), _r("a"), _r("b")]
    assert sort_results(results, "relevance") == results


def test_sort_relevance_is_the_default():
    results = [_r("c"), _r("a"), _r("b")]
    assert sort_results(results) == results


def test_sort_by_name_is_case_insensitive_alphabetical():
    results = [_r("Zebra"), _r("apple"), _r("Banana")]
    sorted_ = sort_results(results, "name")
    assert [r["name"] for r in sorted_] == ["apple", "Banana", "Zebra"]


def test_sort_by_stars_descending():
    results = [_r("low", stars=5), _r("high", stars=100), _r("mid", stars=50)]
    sorted_ = sort_results(results, "stars")
    assert [r["name"] for r in sorted_] == ["high", "mid", "low"]


def test_sort_by_stars_pushes_missing_values_to_the_bottom():
    results = [_r("no-stars"), _r("has-stars", stars=10)]
    sorted_ = sort_results(results, "stars")
    assert [r["name"] for r in sorted_] == ["has-stars", "no-stars"]


def test_sort_by_downloads_descending():
    results = [_r("low", source="huggingface", downloads=1), _r("high", source="huggingface", downloads=999)]
    sorted_ = sort_results(results, "downloads")
    assert [r["name"] for r in sorted_] == ["high", "low"]


def test_sort_by_stars_treats_non_numeric_value_as_missing():
    results = [_r("weird", stars="beaucoup"), _r("normal", stars=3)]
    sorted_ = sort_results(results, "stars")
    assert [r["name"] for r in sorted_] == ["normal", "weird"]


def test_sort_rejects_unknown_option():
    with pytest.raises(ValueError, match="invalide"):
        sort_results([_r("x")], "date")  # jamais offert : aucune source ne fournit de date


def test_sort_does_not_mutate_input_list():
    results = [_r("b", stars=1), _r("a", stars=2)]
    original_order = list(results)
    sort_results(results, "stars")
    assert results == original_order


# --- paginate_results -------------------------------------------------------------------------


def test_paginate_default_page_size():
    assert DEFAULT_PAGE_SIZE == 20


def test_paginate_first_page():
    results = [_r(str(i)) for i in range(25)]
    page_info = paginate_results(results, page=1, page_size=10)
    assert [r["name"] for r in page_info["items"]] == [str(i) for i in range(10)]
    assert page_info["total"] == 25
    assert page_info["total_pages"] == 3


def test_paginate_last_partial_page():
    results = [_r(str(i)) for i in range(25)]
    page_info = paginate_results(results, page=3, page_size=10)
    assert [r["name"] for r in page_info["items"]] == ["20", "21", "22", "23", "24"]


def test_paginate_page_beyond_total_returns_empty():
    results = [_r(str(i)) for i in range(5)]
    page_info = paginate_results(results, page=99, page_size=10)
    assert page_info["items"] == []
    assert page_info["total"] == 5


def test_paginate_empty_results():
    page_info = paginate_results([], page=1, page_size=10)
    assert page_info["items"] == []
    assert page_info["total"] == 0
    assert page_info["total_pages"] == 1


def test_paginate_rejects_zero_or_negative_page():
    with pytest.raises(ValueError):
        paginate_results([_r("x")], page=0)


def test_paginate_rejects_zero_or_negative_page_size():
    with pytest.raises(ValueError):
        paginate_results([_r("x")], page=1, page_size=0)


def test_paginate_single_page_when_fewer_results_than_page_size():
    results = [_r(str(i)) for i in range(3)]
    page_info = paginate_results(results, page=1, page_size=10)
    assert page_info["total_pages"] == 1
    assert len(page_info["items"]) == 3
