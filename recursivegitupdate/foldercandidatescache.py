"""File-based cache to store folder candidates in a private per-user temp directory."""

import getpass
import hashlib
import os
import re
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from time import time

from loguru import logger

from recursivegitupdate.models import CACHE_VERSION, CacheData

__all__ = ["FolderCandidatesCache"]

_CACHE_DIR_PREFIX = "recursivegitupdate-"


def _user_name() -> str:
    """Determine the current user's name in a form that is safe to use as part of a file name."""
    try:
        name = getpass.getuser()
    except (KeyError, OSError):  # no passwd entry / no user information available
        name = str(os.getuid()) if os.name == "posix" else ""
    return re.sub(r"[^\w.-]", "_", name) or "user"


def _private_cache_dir() -> Path | None:
    """Create (if needed) and verify the per-user cache directory below the system's temp directory.

    On POSIX the shared temp directory is writable by everybody, so the directory must be owned by the
    current user and must not be accessible by others. On Windows the temp directory is already per-user,
    thus only the symlink check applies there.

    Returns:
        The directory, or None if it is missing, not usable or not trustworthy.
    """
    cache_dir = Path(tempfile.gettempdir()) / f"{_CACHE_DIR_PREFIX}{_user_name()}"
    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = cache_dir.lstat()  # lstat: do not follow symlinks
        if not stat.S_ISDIR(st.st_mode):
            logger.warning("Cache directory is not a real directory (symlink?): {}", cache_dir)
            return None
        if os.name == "posix":
            if st.st_uid != os.getuid():
                logger.warning("Cache directory belongs to another user: {}", cache_dir)
                return None
            if st.st_mode & 0o077:
                cache_dir.chmod(0o700)
    except OSError as ex:
        logger.warning("Cache directory '{}' is not usable: {}", cache_dir, ex)
        return None
    return cache_dir


class FolderCandidatesCache:
    """File-based cache (JSON) to store folder candidates.

    A disabled cache never reads or writes anything; it behaves like a cache which is always empty.
    """

    def __init__(self, cache_file: Path, outdated_age_max_days: float = 1.0, *, enabled: bool = True):
        """Initialize cache."""
        self.cache_filepath = cache_file
        self.outdated_age_max_days = outdated_age_max_days
        self.enabled = enabled
        logger.debug("cache_file: {}", cache_file.resolve())
        logger.debug("outdated_age_max_days: {:.2f}", outdated_age_max_days)

    @classmethod
    def for_basepath(cls, basepath: Path, outdated_age_max_days: float = 1.0) -> "FolderCandidatesCache":
        """Create the cache for a base path, located in a private per-user directory in the temp folder.

        The file name is derived from the base path, so each base path has its own cache. If no trustworthy
        cache directory is available, a disabled cache is returned.
        """
        key = os.fsencode(os.path.normcase(str(basepath.resolve())))
        filename = f"{hashlib.sha256(key).hexdigest()[:16]}.json"
        cache_dir = _private_cache_dir()
        if cache_dir is None:
            logger.warning("Folder cache is disabled.")
            return cls(Path(tempfile.gettempdir()) / filename, outdated_age_max_days, enabled=False)
        return cls(cache_dir / filename, outdated_age_max_days)

    def update(self, data: CacheData) -> None:
        """Add data to cache (atomically, a concurrent run never sees a partially written file)."""
        if not self.enabled:
            return
        logger.info("Updating cache ...")
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf8", dir=self.cache_filepath.parent, suffix=".tmp", delete=False
            ) as tmp_file:
                tmp_name = tmp_file.name
                tmp_file.write(data.model_dump_json(indent=4))
            # the temp file must be closed before the rename (Windows)
            Path(tmp_name).replace(self.cache_filepath)
        except OSError as ex:  # the cache is only an optimization, never abort because of it
            logger.warning("Failed to write cache file '{}': {}", self.cache_filepath, ex)
            if tmp_name:
                with suppress(OSError):
                    Path(tmp_name).unlink(missing_ok=True)

    def load(self) -> CacheData | None:
        """Load cached data.

        Returns:
            The cached data, or None if the cache is missing, outdated, unreadable or from another program version.
        """
        if not self.enabled or not self.cache_filepath.is_file():
            return None

        if self.get_age() > self.outdated_age_max_days:
            logger.warning("Cache is outdated!")
            return None

        try:
            data = CacheData.model_validate_json(self.cache_filepath.read_text(encoding="utf8"))
        except (OSError, ValueError) as ex:  # includes JSON, Unicode and pydantic validation errors
            logger.error("Failed to read cache file '{}': {}", self.cache_filepath, ex)
            return None

        if data.cache_version != CACHE_VERSION:
            logger.warning(
                "Ignoring invalid cache file: unsupported cache version (expected: {}, actual: {})",
                CACHE_VERSION,
                data.cache_version,
            )
            return None
        return data

    def invalidate(self) -> None:
        """Make the cached data invalid."""
        if self.enabled and self.cache_filepath.is_file():
            logger.info("Invalidating cache by removing cache file.")
            self.cache_filepath.unlink(missing_ok=True)

    def get_age(self) -> float:
        """Determine the age (in days) of the cache file."""
        try:
            cache_stat = self.cache_filepath.stat()
        except OSError as ex:
            logger.exception("Could not stat cache file! {}", ex)
            return float("inf")
        cache_age_days = (time() - cache_stat.st_mtime) / 86400
        logger.debug("Cache file age (days): {:.2f}", cache_age_days)
        return cache_age_days
