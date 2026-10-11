"""Data models: folder candidates, cache payload and update results."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

__all__ = ["CACHE_VERSION", "CacheData", "FolderCandidates", "Results"]

#: Bump whenever the cache layout changes in an incompatible way.
CACHE_VERSION = 5


class FolderCandidates(BaseModel):
    """Immutable collection of RCS (git, svn) folder candidates.

    Accepts any sequence (list, tuple) and converts it to a tuple.
    """

    model_config = ConfigDict(frozen=True)

    git: tuple[Path, ...] = ()
    svn: tuple[Path, ...] = ()
    ignores: tuple[Path, ...] = ()
    #: Subset of ``git`` for which ``git push`` is forbidden (see ``scanner.IGNORE_FILE_NOGITPUSH``).
    git_nopush: tuple[Path, ...] = ()


class CacheData(BaseModel):
    """Payload of the cache file (JSON)."""

    root: Path
    candidates: FolderCandidates
    cache_version: int = CACHE_VERSION


@dataclass
class Results:
    """Accumulated result messages for each category."""

    ok: dict[Path, str] = field(default_factory=dict)
    error: dict[Path, str] = field(default_factory=dict)
    ignored: dict[Path, str] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """Check whether any errors were recorded."""
        return len(self.error) > 0
