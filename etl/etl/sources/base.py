"""Shared row shape every source adapter yields. DATA_PIPELINE.md §Shared shape:
one normalized dict per target table; the loader knows the natural key per table.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawRow:
    """One source row before normalization, tagged with where it came from so a
    quarantined row and a loaded row both carry `source_ref` back to a cell.
    """

    target_table: str
    fields: dict[str, str]
    source_ref: str


class SourceAdapter(Protocol):
    def read_rows(self, source_ref: str) -> Iterator[RawRow]: ...
