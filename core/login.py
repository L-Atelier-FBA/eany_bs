import asyncio
import logging
from playwright.async_api import async_playwright, ProxySettings, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class EanyLogin:
    def __init__(self, email: str, password: str, headless: bool = True, proxy: ProxySettings = None):
        self.login_url = "https://eany.io/login/"
        self.email = email
        self.password = password
        self.headless = headless
        self.proxy = proxy

    async def _run(self) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(proxy=self.proxy)
            page = await context.new_page()

            try:
                await page.goto(self.login_url, wait_until="load", timeout=60000)

                try:
                    await page.locator("#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll").click(timeout=5000)
                except PlaywrightTimeoutError:
                    pass

                await page.fill("input[type='email']", self.email)
                await page.fill("input[type='password']", self.password)
                await page.click("button[type='submit']")

                await page.wait_for_load_state("load")
                await page.wait_for_timeout(10000)

                cookies = await context.cookies()
                return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

            finally:
                await browser.close()

    async def login(self, retries: int = 3):
        for attempt in range(1, retries + 1):
            try:
                logging.info(f"Login attempt {attempt}")
                return await self._run()
            except Exception as e:
                logging.warning(f"Login attempt {attempt} failed: {e}")
                if attempt == retries:
                    raise
                await asyncio.sleep(2 ** attempt)
        return None
