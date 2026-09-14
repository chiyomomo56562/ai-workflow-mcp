"""Load and minimally validate the design contract used by the server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = {"name", "version", "workflow", "tools", "artifacts", "errors"}


def default_spec_path() -> Path:
    return Path(__file__).resolve().parents[2] / "workflow-mcp-spec-v0.2.json"


def load_spec(path: str | Path | None = None) -> dict[str, Any]:
    spec_path = Path(path) if path else default_spec_path()
    with spec_path.open(encoding="utf-8") as spec_file:
        spec = json.load(spec_file)

    missing = REQUIRED_TOP_LEVEL_KEYS - spec.keys()
    if missing:
        missing_keys = ", ".join(sorted(missing))
        raise ValueError(f"Spec is missing required top-level keys: {missing_keys}")
    if spec["name"] != "workflow-mcp" or spec["version"] != "0.2.0":
        raise ValueError("Unsupported workflow-mcp spec")
    return spec

