#!/usr/bin/env python3
"""Write a Gate C metadata manifest from a read-only database connection."""
from __future__ import annotations

import argparse

from .manifest import ManifestError, write_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a metadata-only Gate C manifest")
    parser.add_argument("--database-url", required=True, help="read-only source or target database URL")
    parser.add_argument("--output", required=True, help="new manifest path; existing files are never overwritten")
    args = parser.parse_args()
    try:
        write_manifest(args.database_url, args.output)
    except ManifestError as exc:
        parser.error(str(exc))
    print("result=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
