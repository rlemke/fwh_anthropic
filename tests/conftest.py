"""Pytest configuration: opt-in --run-live flag for live API tests.

Tests marked ``@pytest.mark.live`` hit the real Anthropic API and burn
real tokens. They're skipped by default (via ``addopts = -m 'not live'``
in ``pyproject.toml``). To run them explicitly::

    ANTHROPIC_API_KEY=sk-... pytest -m live --run-live

When ``--run-live`` is omitted, live tests are skipped even if the
``-m live`` filter is active — this catches an easy mistake of running
``-m live`` without intending to spend money.
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run @pytest.mark.live tests against the real Anthropic API.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-live"):
        # User explicitly opted in: just check the key is present.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            skip_no_key = pytest.mark.skip(
                reason="--run-live passed but ANTHROPIC_API_KEY is unset"
            )
            for item in items:
                if "live" in item.keywords:
                    item.add_marker(skip_no_key)
        return

    skip_live = pytest.mark.skip(
        reason="live test — pass --run-live (and set ANTHROPIC_API_KEY) to enable"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
