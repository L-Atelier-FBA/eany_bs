import asyncio
import logging
from typing import Optional, Any, Dict
from curl_cffi.requests import AsyncSession, Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class Requester:
    def __init__(self, token: Optional[str] = None, cookie: Optional[str] = None, proxy: Optional[str] = None):
        self.session: Optional[AsyncSession] = None
        self.proxy = proxy
        self.headers: Dict[str, str] = {
            "Accept": "*/*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Origin": "https://eany.io",
            "Referer": "https://eany.io",
        }
        if token:
            self.headers.update({"Accept": "application/json, text/plain, */*", "Authorization": f"Bearer {token}"})
        if cookie:
            self.headers["Cookie"] = cookie

    async def __aenter__(self):
        extra_params = {"timeout": 60, "allow_redirects": True, "http_version": "v2"}
        self.session = AsyncSession(impersonate="chrome142", headers=self.headers, proxy=self.proxy, **extra_params)
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)

    async def request(self, method, url: str, retries: int = 3, **kwargs: Any) -> Optional[Response]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with Requester(...) as r:'")
        for attempt in range(1, retries + 1):
            try:
                resp = await self.session.request(method, url, **kwargs)
                if resp.status_code < 400:
                    return resp
                logging.warning(f"{method.upper()} {url} returned {resp.status_code} (attempt {attempt})")
            except Exception as e:
                logging.warning(f"{method.upper()} {url} failed (attempt {attempt}): {e}")
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
        logging.error(f"{method.upper()} {url} failed after {retries} attempts")
        return None

    async def fetch_get(self, url: str, **kwargs: Any) -> Optional[Response]:
        return await self.request("GET", url, **kwargs)

    async def fetch_post(self, url: str, data: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[Response]:
        return await self.request("POST", url, data=data, json=json, **kwargs)
