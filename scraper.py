import cloudscraper
from bs4 import BeautifulSoup
import re
import logging
import time

logger = logging.getLogger(__name__)

def _supported_encodings() -> str:
    """Only advertise brotli if we can actually decode it.

    Requesting "br" without the brotli package installed makes Amazon return a
    brotli-compressed body that requests cannot decompress, so response.text is
    binary garbage and every selector silently misses.
    """
    try:
        import brotli  # noqa: F401
    except ImportError:
        try:
            import brotlicffi  # noqa: F401
        except ImportError:
            return "gzip, deflate"
    return "gzip, deflate, br"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    # Ask for English so prices come back in Western digits.
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": _supported_encodings(),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

# Amazon serves a captcha/interstitial instead of the product page when it
# decides the caller is a bot; these markers identify that page.
BOT_BLOCK_MARKERS = (
    "Enter the characters you see below",
    "api-services-support@amazon.com",
    "To discuss automated access to Amazon data",
    "Type the characters you see in this image",
    "/errors/validateCaptcha",
)

scraper = cloudscraper.create_scraper()


def fetch_product(url: str, lang: str = "en", retry_count: int = 0) -> dict | None:
    """
    Scrape an Amazon product page and return name, price, specs, and image.
    Includes retry logic with exponential backoff.

    Args:
        url: Amazon product URL
        lang: Language code ('en' or 'ar')
        retry_count: Internal retry counter (don't set manually)

    Returns None if the page could not be parsed.
    """
    MAX_RETRIES = 2

    try:
        response = scraper.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
    except Exception as e:
        if retry_count < MAX_RETRIES:
            wait_time = 2 ** retry_count
            logger.warning(f"[scraper] Request failed, retrying in {wait_time}s: {e}")
            time.sleep(wait_time)
            return fetch_product(url, lang, retry_count + 1)
        logger.error(f"[scraper] Request failed after {MAX_RETRIES + 1} attempts for {url}: {e}")
        return None

    html = response.text

    logger.info(
        f"[scraper] GET {response.status_code} | "
        f"encoding={response.headers.get('Content-Encoding') or 'none'} | "
        f"bytes={len(html)} | final_url={response.url}"
    )

    if any(marker in html for marker in BOT_BLOCK_MARKERS):
        if retry_count < MAX_RETRIES:
            wait_time = 3 * (retry_count + 1)
            logger.warning(f"[scraper] Amazon returned a bot check, retrying in {wait_time}s")
            time.sleep(wait_time)
            return fetch_product(url, lang, retry_count + 1)
        logger.error(f"[scraper] Amazon is serving a bot check (captcha) for {url}")
        return None

    if not _looks_like_html(html):
        logger.error(
            f"[scraper] Response body is not readable HTML "
            f"(encoding={response.headers.get('Content-Encoding')}). "
            f"First 80 chars: {html[:80]!r}"
        )
        return None

    try:
        soup = BeautifulSoup(html, "lxml")

        name = _extract_name(soup, lang)
        price = _extract_price(soup, html)
        image_url = _extract_image(soup)
        description = _extract_description(soup, lang)
        specs = _extract_specs(soup, lang)

        if price is None:
            has_title = soup.find(id="productTitle") is not None
            logger.error(
                f"[scraper] Could not find price for {url} "
                f"(productTitle present={has_title}, bytes={len(html)}). "
                f"Page layout may have changed or the item is unavailable."
            )
            return None

        logger.info(f"[scraper] OK '{name[:40]}' -> {price:,.2f}")
        return {
            "name": name,
            "price": price,
            "image": image_url,
            "description": description,
            "specs": specs,
            "language": lang,
        }
    except Exception as e:
        logger.exception(f"[scraper] Error parsing page for {url}: {e}")
        return None


def _looks_like_html(body: str) -> bool:
    head = body[:2048].lstrip().lower()
    return "<html" in head or head.startswith("<!doctype") or "<head" in head


def _extract_name(soup: BeautifulSoup, lang: str = "en") -> str:
    """Extract product name from the page."""
    name_tag = soup.find(id="productTitle")
    return name_tag.get_text(strip=True) if name_tag else "Unknown Product"


def _extract_image(soup: BeautifulSoup) -> str | None:
    """Extract product image URL from the page."""
    img_tag = soup.find("img", {"id": "landingImage"})
    if img_tag and img_tag.get("src"):
        return img_tag["src"]

    img_tag = soup.find("img", {"class": "a-dynamic-image"})
    if img_tag and img_tag.get("src"):
        return img_tag["src"]

    return None


def _extract_description(soup: BeautifulSoup, lang: str = "en") -> str | None:
    """Extract product description from the page."""
    desc_selectors = [
        ("div", {"id": "feature-bullets"}),
        ("div", {"class": "a-section a-spacing-medium a-spacing-top-medium"}),
        ("div", {"data-feature-name": "featurebullets"}),
    ]

    for tag, attrs in desc_selectors:
        el = soup.find(tag, attrs)
        if el:
            text = el.get_text(strip=True, separator="\n")
            if text:
                return text[:500]

    return None


def _extract_specs(soup: BeautifulSoup, lang: str = "en") -> dict | None:
    """Extract key product specifications from the page."""
    specs = {}

    details_table = soup.find("table", {"class": "a-keyvalue"})
    if details_table:
        rows = details_table.find_all("tr")
        for row in rows[:5]:
            cells = row.find_all("td")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                specs[key] = value

    return specs if specs else None


# Ordered most-specific first: the buy-box / core price blocks come before the
# generic ones, because the first `.a-offscreen` on a page is frequently the
# struck-through list price rather than the price actually being charged.
PRICE_SELECTORS = (
    "#corePriceDisplay_desktop_feature_div span.priceToPay span.a-offscreen",
    "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
    "#corePrice_feature_div span.a-price span.a-offscreen",
    "#corePrice_desktop span.a-price span.a-offscreen",
    "#apex_desktop span.priceToPay span.a-offscreen",
    "#apex_desktop span.a-price span.a-offscreen",
    "span.priceToPay span.a-offscreen",
    "span.reinventPricePriceToPayMargin span.a-offscreen",
    "#price_inside_buybox",
    "#newBuyBoxPrice",
    "#buybox span.a-price span.a-offscreen",
    "#tp_price_block_total_price_ww span.a-offscreen",
    "#sns-base-price",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#priceblock_saleprice",
    "#usedBuySection span.a-color-price",
    # Whole/fraction pair — handled specially below.
    "#corePriceDisplay_desktop_feature_div span.a-price-whole",
    "span.a-price span.a-price-whole",
    # Last resort: any price on the page.
    "span.a-price span.a-offscreen",
    "span.a-color-price",
)

# Amazon embeds the authoritative price in its inline JSON payloads.
PRICE_JSON_PATTERNS = (
    r'"priceAmount"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
    r'"displayPrice"\s*:\s*"[^"0-9]*([0-9][0-9.,]*)"',
    r'"buyingPrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
)


def _extract_price(soup: BeautifulSoup, html: str | None = None) -> float | None:
    for selector in PRICE_SELECTORS:
        el = soup.select_one(selector)
        if not el:
            continue

        raw = el.get_text(strip=True)

        # `a-price-whole` holds only the integer part; the decimals live in a
        # sibling `a-price-fraction`. Without stitching them together a price of
        # 1,299.99 would be read as 1299 — or as 129999 once separators are
        # stripped, depending on the trailing separator Amazon renders.
        if "a-price-whole" in (el.get("class") or []):
            fraction = el.find_next("span", {"class": "a-price-fraction"})
            whole = re.sub(r"[^\d]", "", _normalize_digits(raw))
            if whole:
                if fraction:
                    frac_digits = re.sub(r"[^\d]", "", _normalize_digits(fraction.get_text(strip=True)))
                    raw = f"{whole}.{frac_digits or '0'}"
                else:
                    raw = whole

        price = _parse_price(raw)
        if price is not None:
            logger.debug(f"[scraper] Price matched via '{selector}': {price}")
            return price

    if html:
        for pattern in PRICE_JSON_PATTERNS:
            match = re.search(pattern, html)
            if match:
                price = _parse_price(match.group(1))
                if price is not None:
                    logger.debug(f"[scraper] Price matched via JSON pattern: {price}")
                    return price

    return None


# Amazon's Arabic locale renders prices in Arabic-Indic digits, which float()
# cannot parse.
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _normalize_digits(raw: str) -> str:
    return raw.translate(_ARABIC_INDIC)


def _parse_price(raw: str) -> float | None:
    """Extract a float from a string like 'EGP 1,299.00', '1,299' or '١٢٩٩'."""
    cleaned = _normalize_digits(raw)
    cleaned = re.sub(r"[^\d.,]", "", cleaned)      # keep digits, dot, comma
    cleaned = cleaned.strip(".,")                   # drop dangling separators

    if not cleaned:
        return None

    # Decide which separator is the decimal point: whichever comes last, and
    # only when it is followed by 1-2 digits (thousands groups are always 3).
    last_dot, last_comma = cleaned.rfind("."), cleaned.rfind(",")
    decimal_sep = None
    if last_dot > last_comma and len(cleaned) - last_dot - 1 in (1, 2):
        decimal_sep = "."
    elif last_comma > last_dot and len(cleaned) - last_comma - 1 in (1, 2):
        decimal_sep = ","

    if decimal_sep:
        whole, _, frac = cleaned.rpartition(decimal_sep)
        cleaned = re.sub(r"[^\d]", "", whole) + "." + frac
    else:
        cleaned = re.sub(r"[^\d]", "", cleaned)

    try:
        price = float(cleaned)
    except ValueError:
        return None

    # Guard against parsing something that is not a price at all.
    if price <= 0 or price > 100_000_000:
        return None
    return price
