"""Convert the approved YAML contract to deterministic JSON."""

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
YAML_CONTRACT = ROOT / "docs" / "api" / "openapi.yaml"
JSON_CONTRACT = ROOT / "docs" / "api" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    if args.contract_only:
        document = yaml.safe_load(YAML_CONTRACT.read_text(encoding="utf-8"))
    else:
        from app.main import app

        document = app.openapi()
    JSON_CONTRACT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
