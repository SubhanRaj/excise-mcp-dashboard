"""CSV / local & network shares. DATA_PIPELINE.md §Source adapters: csv stdlib +
explicit dialect; a registry row can point at a directory glob, each file keyed
by path + mtime + size (change detection is the caller's job, not this reader's).
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from etl.sources.base import RawRow


def read_rows(source_ref: str, target_table: str, encoding: str = "utf-8-sig") -> Iterator[RawRow]:
    path = Path(source_ref)
    with path.open(newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            yield RawRow(
                target_table=target_table,
                fields={k: (v or "") for k, v in row.items()},
                source_ref=f"csv:{source_ref}:{i}",
            )
