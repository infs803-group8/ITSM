"""Export runtime OpenAPI JSON."""

import json
from pathlib import Path

from app.main import app


def export_openapi(target: Path) -> None:
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
