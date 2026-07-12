import cloudscraper
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

scraper = cloudscraper.create_scraper()


def fetch_product(url: str, lang: str = "en") -> dict | None:
    """
    Scrape an Amazon product page and return name, price, specs, and image.
    Supports multiple languages by parsing the page content.

    Args:
        url: Amazon product URL
        lang: Language code ('en' or 'ar')

    Returns None if the page could not be parsed.
    """
    try:
        response = scraper.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[scraper] Request failed for {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, "lxml")

    name = _extract_name(soup, lang)
    price = _extract_price(soup)
    image_url = _extract_image(soup)
    description = _extract_description(soup, lang)
    specs = _extract_specs(soup, lang)

    if price is None:
        print(f"[scraper] Could not find price for: {url}")
        return None

    return {
        "name": name,
        "price": price,
        "image": image_url,
        "description": description,
        "specs": specs,
        "language": lang,
    }


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


def _extract_price(soup: BeautifulSoup) -> float | None:
    selectors = [
        # Main price box (whole + fraction)
        ("span", {"class": "a-price-whole"}),
        # Deals / sale price
        ("span", {"id": "priceblock_dealprice"}),
        # Regular price
        ("span", {"id": "priceblock_ourprice"}),
        # Generic price span
        ("span", {"class": "a-offscreen"}),
    ]

    for tag, attrs in selectors:
        el = soup.find(tag, attrs)
        if el:
            raw = el.get_text(strip=True)
            price = _parse_price(raw)
            if price is not None:
                return price

    return None


def _parse_price(raw: str) -> float | None:
    """Extract a float from a string like 'EGP 1,299.00' or '1,299'."""
    cleaned = re.sub(r"[^\d.,]", "", raw)          # keep digits, dot, comma
    cleaned = cleaned.replace(",", "")              # remove thousands separator
    cleaned = cleaned.rstrip(".")                   # remove trailing dot
    try:
        return float(cleaned)
    except ValueError:
        return None
