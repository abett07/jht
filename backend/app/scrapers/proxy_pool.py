import os
import itertools
from typing import Iterator, List, Optional


_PROXY_CYCLE: Optional[Iterator[str]] = None


def _load_proxies() -> List[str]:
    # Single proxy env variable takes precedence
    p = os.getenv('PLAYWRIGHT_PROXY')
    if p:
        return [p]
    multi = os.getenv('PLAYWRIGHT_PROXIES')
    if multi:
        # comma-separated list
        return [x.strip() for x in multi.split(',') if x.strip()]
    # optional proxies file
    path = os.getenv('PLAYWRIGHT_PROXIES_FILE')
    if path and os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip()]
    return []


def get_proxy() -> Optional[str]:
    """Return next proxy string in round-robin, or None if none configured."""
    global _PROXY_CYCLE
    if _PROXY_CYCLE is None:
        proxies = _load_proxies()
        if not proxies:
            return None
        _PROXY_CYCLE = itertools.cycle(proxies)
    try:
        return next(_PROXY_CYCLE)
    except StopIteration:
        return None
