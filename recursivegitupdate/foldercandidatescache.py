# -*- coding: utf-8 -*-
"""File-based cache to store folder candidates."""
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Dict, List

CACHE_VERSION = 3


@dataclass
class CacheData:
    """Cache data structure / data model."""

    root: Path
    candidates: Dict[str, List[Path]]
    cache_version: int = CACHE_VERSION


class FolderCandidatesCache:
    """File-based cache (JSON) to store folder candidates."""

    # default file name of the cache file.
    CACHE_FILE = ".recursive_rcs_update.cache"

    def __init__(self, cache_file: Path = CACHE_FILE, outdated_age_max_days: float = 1.0):
        """Initialize cache."""
        self.cache_filepath = cache_file
        self.outdated_age_max_days = outdated_age_max_days
        logging.debug("cache_file: %s", cache_file.resolve())
        logging.debug("outdated_age_max_days: %.2f", outdated_age_max_days)

    def update(self, data: CacheData):
        """Add data to cache."""
        logging.info("Updating cache ...")
        self.__write(data)

    def load(self) -> CacheData | None:
        """Load cached data."""
        if self.cache_filepath.is_file():
            if self.__is_outdated():
                logging.warning("Cache is outdated!")
                return None
            # else
            data = self.__read()
            self.__check_version(data)
            # convert simple strings to Path
            data.root = Path(data.root)
            for vlist in data.candidates.values():
                for i, v in enumerate(vlist):
                    vlist[i] = Path(v)
            return data
        # else
        return None

    def invalidate(self):
        """Make the cached data invalid."""
        if self.cache_filepath.is_file():
            logging.info("Invalidating cache by removing cache file.")
            os.unlink(self.cache_filepath)

    def __write(self, data: CacheData):
        # Custom dict_factory function to convert Path objects to strings recursively
        def custom_dict_factory(data):
            def convert_value(value):
                if isinstance(value, Path):
                    # Convert Path to string
                    return str(value)
                if isinstance(value, list):
                    # Recursively handle lists
                    return [convert_value(v) for v in value]
                if isinstance(value, dict):
                    # Recursively handle dicts
                    return {k: convert_value(v) for k, v in value.items()}
                # Return other values unchanged
                return value

            # Apply conversion to all key-value pairs
            return {k: convert_value(v) for k, v in data}

        data_dict = asdict(data, dict_factory=custom_dict_factory)

        with self.cache_filepath.open("w", encoding="utf8") as fout:
            json.dump(data_dict, fout, indent=4)

    def __read(self) -> CacheData:
        with self.cache_filepath.open("r", encoding="utf8") as fin:
            data_dict = json.load(fin)
        data = CacheData(
            root=data_dict["root"],
            candidates=data_dict["candidates"],
            cache_version=data_dict["cache_version"]
        )
        return data

    def __is_outdated(self) -> bool:
        """Check if cache is older than x days."""
        cache_age_days = self.get_age()
        return cache_age_days > self.outdated_age_max_days

    def get_age(self) -> float:
        """Determine the age (in days) of the cache file."""
        try:
            cache_stat = self.cache_filepath.stat()
            cache_age_days = (time() - cache_stat.st_mtime) / 3600 / 24
            logging.debug("Cache file age (days): %.02f", cache_age_days)
            return cache_age_days
        except IOError as ex:
            logging.exception("Could not stat cache file! %s", ex)
            return sys.maxsize

    @staticmethod
    def __check_version(data):
        try:
            version = int(data.cache_version)
            logging.debug("Cache version: %d", version)
        except Exception as ex:
            raise RuntimeError("Invalid cache - could not read version field!", ex) from ex
        if version != CACHE_VERSION:
            raise RuntimeError(f"Invalid cache version! expected:{CACHE_VERSION}, actual:{version}")
