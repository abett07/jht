
from playwright.sync_api import sync_playwright
import time
from typing import Optional
from .proxy_pool import get_proxy


class PlaywrightRunner:
    """Context manager for a Playwright browser with simple retry and proxy rotation.

    If `proxy` is None and proxies are configured via env, PlaywrightRunner will rotate
    proxies until a browser launches successfully (up to `max_attempts`).
    """

    def __init__(self, proxy: Optional[str] = None, headless: bool = True, max_attempts: int = 3, backoff: float = 2.0):
        self.proxy = proxy
        self.headless = headless
        self.max_attempts = max_attempts
        self.backoff = backoff
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        attempt = 0
        last_err = None
        # If proxy was not provided, use rotating proxies from pool
        while attempt < self.max_attempts:
            attempt += 1
            p = self.proxy or get_proxy()
            try:
                launch_args = {"headless": self.headless}
                if p:
                    launch_args["proxy"] = {"server": p}
                self._browser = self._pw.chromium.launch(**launch_args)
                self._context = self._browser.new_context()
                return self
            except Exception as e:
                last_err = e
                # close partial resources, then wait and retry
                try:
                    if self._browser:
                        self._browser.close()
                except Exception:
                    pass
                time.sleep(self.backoff * attempt)
                continue

        # if we exit loop without returning, raise last error
        raise last_err if last_err else RuntimeError("Failed to start Playwright browser")

    def new_page(self):
        if not self._context:
            raise RuntimeError("Browser context not initialized")
        return self._context.new_page()

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass
        finally:
            try:
                if self._browser:
                    self._browser.close()
            finally:
                if self._pw:
                    self._pw.stop()
