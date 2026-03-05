#!/usr/bin/env python3
"""Generate a revision manifest JSON file for ATHENA-rods builds."""

from __future__ import annotations

import argparse
from pathlib import Path

from arod_common.versioning import write_revision_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build") / "revision_manifest.json",
        help="Output JSON path (default: build/revision_manifest.json)",
    )
    parser.add_argument(
        "--context",
        default="manual",
        help="Free-form context label included in the manifest",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = write_revision_manifest(args.output, extra={"context": args.context})
    print(f"Wrote revision manifest: {args.output}")
    print(f"version={record['version']} git_revision={record['git_revision']} dirty={record['git_dirty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
