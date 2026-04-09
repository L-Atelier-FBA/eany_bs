import asyncio
import logging
import json
import os
from dotenv import load_dotenv
from core.requester import Requester
from core.login import EanyLogin

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

JSON_FILE = "products.json"
STATE_FILE = "category_state.json"
CONCURRENT_REQUESTS = 100
RETRIES = 3
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

CATEGORIES = [
    "https://backend.eany.io/api/v1/products?category=537&page={}",
    "https://backend.eany.io/api/v1/products?category=111&page={}",
    "https://backend.eany.io/api/v1/products?category=141&page={}",
    "https://backend.eany.io/api/v1/products?category=222&page={}",
    "https://backend.eany.io/api/v1/products?category=632&page={}",
    "https://backend.eany.io/api/v1/products?category=469&page={}",
    "https://backend.eany.io/api/v1/products?category=536&page={}",
    "https://backend.eany.io/api/v1/products?category=922&page={}",
    "https://backend.eany.io/api/v1/products?category=2092&page={}",
    "https://backend.eany.io/api/v1/products?category=988&page={}",
    "https://backend.eany.io/api/v1/products?category=1239&page={}",
    "https://backend.eany.io/api/v1/products?category=888&page={}"
]

def load_state():
    if not os.path.exists(STATE_FILE):
        return 0
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f).get("current_index", 0)
    except Exception:
        return 0

def save_state(index):
    with open(STATE_FILE, "w") as f:
        json.dump({"current_index": index}, f)

async def scrape_page(session, semaphore, url, page, existing_keys, lock):
    async with semaphore:
        for attempt in range(RETRIES):
            try:
                response = await session.fetch_get(url)
                if response and response.status_code == 200:
                    try:
                        resp = json.loads(response.text)
                    except json.JSONDecodeError:
                        raise ValueError("Invalid JSON response")
                    data = resp.get("data", [])
                    last_page = resp.get("pagination", {}).get("last", 1)

                    page_products = []
                    skipped = {"no_name": 0, "invalid_id": 0, "dup": 0}

                    async with lock:
                        for i in data:
                            name = (i.get("name") or "").strip()
                            gtin = (i.get("ean") or "").strip()
                            asin = (i.get("asin") or "").strip()
                            stocks = i.get("stocks") or []
                            price = stocks[0].get("unit_price_net") if stocks and "unit_price_net" in stocks[0] else None

                            if not name:
                                skipped["no_name"] += 1
                                continue
                            if not (gtin.isdigit() and len(gtin) == 13):
                                gtin = None
                            if len(asin) != 10:
                                asin = None
                            if not gtin or not asin:
                                skipped["invalid_id"] += 1
                                continue

                            unique_key = f"{gtin}_{asin}"
                            if unique_key in existing_keys:
                                skipped["dup"] += 1
                                continue

                            existing_keys.add(unique_key)
                            product_link = f"https://eany.io/product/{gtin}"
                            page_products.append({
                                "product_name": name,
                                "product_gtin": gtin,
                                "supplier_price": price,
                                "product_link": product_link,
                                "asin": asin
                            })

                    logger.info(
                        f"Page {page} new {len(page_products)} | "
                        f"no_name {skipped['no_name']} | "
                        f"invalid_id {skipped['invalid_id']} | "
                        f"dup {skipped['dup']}"
                    )
                    return page_products, last_page
                else:
                    logger.warning(f"Page {page} status {getattr(response, 'status_code', None)}")
            except Exception as e:
                logger.warning(f"Page {page} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2 ** attempt)
        return [], None

async def eany_scraper():
    if not EMAIL or not PASSWORD:
        raise ValueError("Missing EMAIL or PASSWORD in .env")

    login = EanyLogin(email=EMAIL, password=PASSWORD, headless=True)
    cookies = await login.login()
    if not cookies:
        raise RuntimeError("Login failed")

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    lock = asyncio.Lock()
    existing_keys = set()
    product_data = []

    async with Requester(proxy=os.getenv("PROXY"), cookie=cookies) as session:
        auth_resp = await session.fetch_get("https://eany.io/api/auth/session")
        auth_token = json.loads(auth_resp.text)["token"]

    current_index = load_state()
    category_template = CATEGORIES[current_index]

    async with Requester(proxy=os.getenv("PROXY"), token=auth_token) as session:
        first_url = category_template.format(1)
        first_page, last_page = await scrape_page(session, semaphore, first_url, 1, existing_keys, lock)
        product_data.extend(first_page)
        if not last_page:
            last_page = 1

        tasks = [scrape_page(session, semaphore, category_template.format(p), p, existing_keys, lock)
                 for p in range(2, last_page + 1)]
        results = await asyncio.gather(*tasks)
        for r, _ in results:
            product_data.extend(r)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(product_data, f, ensure_ascii=False, indent=4)

    save_state((current_index + 1) % len(CATEGORIES))
    logger.info(f"Scraping complete. Saved {len(product_data)} products.")

if __name__ == "__main__":
    asyncio.run(eany_scraper())
