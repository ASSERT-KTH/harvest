#!/usr/bin/python

import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

from harvest import *


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self):
        for stream in self._streams:
            stream.flush()


def _build_cache_output_path(now=None, cache_root=None):
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    cache_dir = cache_root or (Path(__file__).resolve().parent / "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"notify_chains_{timestamp}.log"


def notify_for_keyword_chains():
    """
    python -c "import harvest; harvest.notify_for_keyword_chains()"
    """
    cache_path = _build_cache_output_path()
    with cache_path.open("w", encoding="utf-8") as cache_file:
        try:
            with redirect_stdout(_Tee(sys.stdout, cache_file)), redirect_stderr(
                _Tee(sys.stderr, cache_file)
            ):
                return notify_for_all_keyword("Chains")
        finally:
            print(f"Saved output to {cache_path}")


if __name__ == "__main__":
    notify_for_keyword_chains()
