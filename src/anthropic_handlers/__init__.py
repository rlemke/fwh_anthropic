"""Anthropic integration example package — Facetwork FFL + handlers
that wrap the public surfaces published at https://github.com/anthropics.

The package is **multi-area by design**: every distinct Anthropic
surface (Messages API, Batch API, Files API, Agent SDK, Claude Code,
Computer Use, MCP, evaluations, cookbook recipes, …) lives in its own
subpackage under ``handlers/`` and ``tools/_lib/``. Areas can grow
independently — adding a new one is purely additive (no need to touch
existing areas' code).

Discovered by the Facetwork runner via the ``facetwork.domains`` entry
point declared in ``pyproject.toml``::

    [project.entry-points."facetwork.domains"]
    anthropic = "anthropic_handlers:domain"

Once ``pip install -e .`` has been run from this repository, Facetwork's
``scripts/start-runner --example anthropic`` and ``scripts/seed-examples``
will pick this package up automatically.

At this initial scaffolding stage the package registers **zero**
handlers — each area subpackage contains a stub ``register_handlers``
that's wired into ``register_all_registry_handlers`` and ready to be
filled in. See ``CLAUDE.md`` for the per-area authoring contract.
"""

from __future__ import annotations

from pathlib import Path

from facetwork.domains import DomainPackage

from .handlers import register_all_registry_handlers

domain = DomainPackage(
    name="anthropic",
    ffl_dir=Path(__file__).parent / "ffl",
    register_handlers=register_all_registry_handlers,
)
