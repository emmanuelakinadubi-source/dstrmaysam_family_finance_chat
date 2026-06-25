"""
Event-aware vendor and hotel scraper.

Web search strategy (automated URL discovery):
  Tool: duckduckgo-search (free, no API key, returns real web URLs)

Pipeline per event:
  1.  Geocode event postcode → (lat, lng)  via postcodes.io (free, no key)
  2a. DuckDuckGo search → discover vendor website URLs automatically
  2b. Snippet-first extraction (no HTTP) → build vendor from title+snippet
  2c. Full page scrape only for URLs with no postcode in snippet
  2d. Try to geocode extracted postcodes → assign real distance_km
  2e. Flag delivery_available if vendor is beyond DELIVERY_THRESHOLD_KM
  3.  Yell.com UK business directory scrape (hotels, restaurants, caterers)
  4.  OSM Overpass → fill in precise geo-located vendors within the radius
      (queries node + way + relation so UK hotel building footprints are found)
  5.  feedr.co via Playwright (optional, richer catering data)
  6.  Return combined list sorted by (distance, delivery status)
      pipeline.py then applies guardrails; vendor_indexer.py stores in ChromaDB

Delivery rule:
  distance_km > DELIVERY_THRESHOLD_KM → delivery_available = True
  distance_km == 0 (unknown, web-scraped)  → delivery_available = True (assumed)
  distance_km <= DELIVERY_THRESHOLD_KM    → delivery_available = False (attend in person)
"""
from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_OVERPASS_URL   = "https://overpass-api.de/api/interpreter"
_POSTCODES_IO   = "https://api.postcodes.io/postcodes/{}"

# Vendors beyond this distance must offer delivery to be included
DELIVERY_THRESHOLD_KM = 10.0

# Max DuckDuckGo results to collect per search query
_DDG_RESULTS_PER_QUERY = 12

# Domains that are not individual business pages — skip (ads, social, etc.)
# NOTE: yell.com, yelp, tripadvisor, booking.com are USEFUL for discovery
# so they are intentionally NOT in this block-list
_SKIP_DOMAINS = {
    "google.com", "google.co.uk",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "reddit.com",
    "checkatrade.com", "rated.people.com",
    "companieshouse.gov.uk", "gov.uk",
}

# Delivery platform domains — flag vendor as delivery-capable automatically
_DELIVERY_PLATFORM_DOMAINS = {
    "deliveroo.co.uk", "ubereats.com", "just-eat.co.uk",
    "feedr.co", "hungryhouse.co.uk", "orderoo.co.uk",
    "restaurantguru.com", "menulog.com.au",
}

# Cuisine tags that map to dietary categories used in event briefs
_DIET_TAG_MAP = {
    "vegetarian": ["vegetarian", "vegetarian;vegan", "vegan"],
    "vegan":      ["vegan", "vegetarian;vegan"],
    "halal":      ["halal"],
    "kosher":     ["kosher"],
    "gluten_free": ["gluten_free", "gluten-free"],
}

# OSM amenity/shop tags we treat as food vendors — wide net, budget guardrail filters later
_CATERING_TAGS = [
    # Sit-down & event catering
    '"amenity"="restaurant"',
    '"amenity"="cafe"',
    '"amenity"="catering"',
    '"amenity"="food_court"',
    # Fast food & chains (McDonald's, KFC, Subway, etc.)
    '"amenity"="fast_food"',
    # Pubs/bars that serve food
    '"amenity"="pub"',
    '"amenity"="bar"',
    # Ice cream, desserts, snacks
    '"amenity"="ice_cream"',
    '"amenity"="confectionery"',
    # Shops with food products for bulk orders
    '"shop"="deli"',
    '"shop"="bakery"',
    '"shop"="butcher"',
    '"shop"="supermarket"',
    '"shop"="convenience"',
    '"shop"="greengrocer"',
    '"shop"="fishmonger"',
    '"shop"="cheese"',
    '"shop"="chocolate"',
    '"shop"="confectionery"',
    '"shop"="pasta"',
    '"shop"="food"',
]

# OSM tags for accommodation — expanded to catch way/relation tagged hotels
_HOTEL_TAGS = [
    '"tourism"="hotel"',
    '"tourism"="guest_house"',
    '"tourism"="hostel"',
    '"tourism"="motel"',
    '"tourism"="apartment"',
    '"tourism"="chalet"',
    '"building"="hotel"',
    '"amenity"="conference_centre"',
    '"leisure"="conference_centre"',
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class EventScraperConfig:
    """Everything the scraper needs, extracted from the uploaded event brief."""
    postcode: str
    city: str = ""
    attendees: int = 0
    total_budget: float = 0.0
    catering_budget: float = 0.0       # 0 = derive from total_budget
    hotel_budget: float = 0.0          # 0 = derive from total_budget
    radius_km: float = 5.0             # max 100.0
    food_required: bool = True
    hotel_required: bool = True
    food_categories: List[str] = field(default_factory=list)
    event_id: Optional[str] = None


@dataclass
class ScrapedVendor:
    name: str
    vendor_type: str                       # "catering" | "hotel"
    address: str = ""
    postcode: str = ""
    lat: float = 0.0
    lng: float = 0.0
    distance_km: float = 0.0
    delivery_available: bool = False       # True if vendor can deliver to event postcode
    price_per_head: Optional[float] = None
    price_range: str = ""
    specializations: List[str] = field(default_factory=list)
    cuisine: str = ""
    rating: Optional[float] = None
    phone: str = ""
    website: str = ""
    opening_hours: str = ""
    description: str = ""
    osm_id: str = ""
    source: str = "overpass"              # "overpass" | "web_search" | "feedr.co"


# ── Geocoding ─────────────────────────────────────────────────────────────────

def postcode_to_coords(postcode: str) -> tuple[float, float]:
    """Convert a UK postcode to (lat, lng) using postcodes.io (free, no key)."""
    clean = postcode.replace(" ", "").upper()
    resp = requests.get(
        _POSTCODES_IO.format(clean),
        timeout=10,
        headers={"User-Agent": "EventManagerApp/1.0"},
    )
    data = resp.json()
    if data.get("status") == 200:
        r = data["result"]
        return float(r["latitude"]), float(r["longitude"])
    raise ValueError(f"Could not geocode postcode '{postcode}': {data.get('error')}")


def _try_geocode_postcode(postcode: str) -> Optional[tuple[float, float]]:
    """Non-fatal version — returns None if postcode invalid."""
    try:
        return postcode_to_coords(postcode)
    except Exception:
        return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ── DuckDuckGo web search ─────────────────────────────────────────────────────

def _build_search_queries(config: EventScraperConfig) -> List[str]:
    """
    Keep to ≤5 queries total — DDG rate-limits aggressively when many queries
    are fired in quick succession from the same IP.
    """
    city = (config.city or config.postcode).strip()
    queries: List[str] = []

    if config.food_required:
        queries.append(f"event catering company {city}")
        cats_str = " ".join(config.food_categories[:2]) if config.food_categories else ""
        if cats_str:
            queries.append(f"{cats_str} catering delivery {city}")

    if config.hotel_required:
        queries.append(f"Premier Inn Travelodge Holiday Inn {city}")
        queries.append(f"hotel accommodation {city} group booking")

    if not queries:
        queries.append(f"restaurants hotels near {city}")

    return queries[:5]   # hard cap to avoid rate limiting


def _ddg_search(query: str, max_results: int = _DDG_RESULTS_PER_QUERY) -> List[dict]:
    """
    Run a DuckDuckGo text search and return [{title, href, body}] results.
    Uses duckduckgo-search Python package (free, no key).
    """
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        logger.info("DDG '%s' → %d results", query[:60], len(results))
        return results
    except ImportError:
        logger.warning("duckduckgo_search not installed — web search disabled")
        return []
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []


def _collect_vendor_urls(config: EventScraperConfig) -> List[dict]:
    """
    Run all DDG queries and collect unique, scrapable vendor URLs.

    Returns list of {url, title, snippet, is_delivery_platform, query}.
    Skips social media, ads, and known irrelevant domains.
    """
    queries = _build_search_queries(config)
    seen_urls: set[str] = set()
    collected: List[dict] = []

    for query in queries:
        results = _ddg_search(query)
        time.sleep(2.5)   # DDG rate-limits hard at <1s intervals

        for r in results:
            url = r.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            domain = urlparse(url).netloc.replace("www.", "")
            is_delivery_platform = domain in _DELIVERY_PLATFORM_DOMAINS

            # Skip social media, government sites, generic search results
            if domain in _SKIP_DOMAINS:
                continue
            if any(skip in url for skip in ["/search?", "/maps/", "youtube.com", "reddit.com",
                                             "/ads?", "doubleclick.net"]):
                continue

            collected.append({
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "domain": domain,
                "is_delivery_platform": is_delivery_platform,
                "query": query,
            })

    logger.info("URL discovery: %d unique vendor URLs found", len(collected))
    return collected


# ── Web page scraper ──────────────────────────────────────────────────────────

_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b", re.IGNORECASE
)
_PHONE_RE = re.compile(
    r"(?:(?:\+44|0)[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})"
)
_PRICE_RE = re.compile(r"£(\d+(?:\.\d{1,2})?)")

# Nominatim — OSM's free geocoding service (no API key, 1 req/sec limit)
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Cache to avoid hitting Nominatim twice for the same address string
_geocode_cache: dict[str, Optional[tuple[float, float]]] = {}


def geocode_address(address: str, city_hint: str = "UK") -> Optional[tuple[float, float]]:
    """
    Geocode a street address using Nominatim (OSM).  Free, no key needed.
    Returns (lat, lng) or None.

    Rate limit: 1 request / second — we add a short sleep before each call.
    Results are cached in-process to avoid duplicate requests.
    """
    if not address or len(address) < 5:
        return None

    # Append city hint if it's not already in the address
    query = address if city_hint.lower() in address.lower() else f"{address}, {city_hint}"

    if query in _geocode_cache:
        return _geocode_cache[query]

    time.sleep(1.1)   # Nominatim rate limit: 1 req/sec
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "gb"},
            timeout=10,
            headers={"User-Agent": "EventManagerApp/1.0 (events@company.com)"},
        )
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            _geocode_cache[query] = (lat, lng)
            return lat, lng
    except Exception as exc:
        logger.debug("Nominatim geocode failed for '%s': %s", query, exc)

    _geocode_cache[query] = None
    return None


def _extract_address_from_page(soup, full_text: str) -> str:
    """
    Extract the most complete address string from a vendor web page.

    Priority:
      1. Schema.org JSON-LD  (most structured — used by Google-indexed businesses)
      2. Microdata itemprop attributes
      3. Common HTML patterns (footer address, contact sections)
      4. Regex pattern matching on visible text
    """
    import json as _json

    # ── 1. Schema.org JSON-LD ─────────────────────────────────────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            # Handle both single object and @graph array
            items = data if isinstance(data, list) else [data]
            for item in items:
                addr = item.get("address") or {}
                if isinstance(addr, str) and len(addr) > 5:
                    return addr
                if isinstance(addr, dict):
                    parts = [
                        addr.get("streetAddress", ""),
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("postalCode", ""),
                    ]
                    combined = ", ".join(p for p in parts if p)
                    if combined:
                        return combined
        except Exception:
            pass

    # ── 2. Microdata itemprop ─────────────────────────────────────────────────
    parts = []
    for prop in ["streetAddress", "addressLocality", "addressRegion", "postalCode"]:
        tag = soup.find(attrs={"itemprop": prop})
        if tag:
            parts.append(tag.get_text(strip=True))
    if parts:
        return ", ".join(p for p in parts if p)

    # ── 3. <address> HTML tag ─────────────────────────────────────────────────
    addr_tag = soup.find("address")
    if addr_tag:
        text = addr_tag.get_text(", ", strip=True)
        if len(text) > 10:
            return text

    # ── 4. Footer / contact heuristic ────────────────────────────────────────
    for selector in ["footer", "[class*='contact']", "[class*='address']",
                     "[id*='contact']", "[id*='address']", "[class*='footer']"]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            # Look for a UK postcode inside the element — signals an address block
            if _UK_POSTCODE_RE.search(text):
                # Take the sentence/line containing the postcode
                for line in text.split("\n"):
                    if _UK_POSTCODE_RE.search(line) and len(line) > 8:
                        return line.strip()

    # ── 5. Regex: find lines that look like UK addresses in visible text ──────
    # Pattern: starts with a number or "Unit", contains a comma, ends with postcode
    _ADDR_LINE_RE = re.compile(
        r"(\d+[\w\s,\-\.]+(?:Street|Road|Lane|Avenue|Drive|Close|Way|Court|Park|"
        r"Gardens|Place|Square|Row|Hill|Green|Estate|Business Park)[,\s]+[\w\s]+)",
        re.IGNORECASE,
    )
    match = _ADDR_LINE_RE.search(full_text)
    if match:
        return match.group(1).strip()[:200]

    return ""


def _scrape_url(url_info: dict, event_lat: float, event_lng: float) -> Optional[ScrapedVendor]:
    """
    Scrape a single vendor website and extract structured data.
    Returns None if the page yields nothing useful.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("httpx/beautifulsoup4 not installed — web scraping disabled")
        return None

    url = url_info["url"]
    try:
        resp = httpx.get(url, timeout=15, headers=_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts, styles, nav, footer to focus on content
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Name: prefer <title> or first <h1>
        name = ""
        if soup.title and soup.title.string:
            name = soup.title.string.strip().split("|")[0].split("–")[0].split("-")[0].strip()
        if not name:
            h1 = soup.find("h1")
            if h1:
                name = h1.get_text(strip=True)
        if not name:
            name = url_info.get("title", "").split("|")[0].strip()
        if not name or len(name) < 3:
            return None

        full_text = soup.get_text(" ", strip=True)
        text_lower = full_text.lower()

        # ── Address extraction (schema.org → microdata → HTML → regex) ───────
        address = _extract_address_from_page(soup, full_text)

        # ── Postcode: from page text first, then from extracted address ───────
        postcode_matches = _UK_POSTCODE_RE.findall(full_text)
        vendor_postcode = postcode_matches[0].upper() if postcode_matches else ""
        if not vendor_postcode and address:
            pc_in_addr = _UK_POSTCODE_RE.findall(address)
            if pc_in_addr:
                vendor_postcode = pc_in_addr[0].upper()

        # ── Geocoding: postcode first, then fall back to full address ─────────
        dist_km = 0.0
        v_lat, v_lng = 0.0, 0.0
        geocode_method = "none"

        if vendor_postcode:
            coords = _try_geocode_postcode(vendor_postcode)
            if coords:
                v_lat, v_lng = coords
                dist_km = round(haversine_km(event_lat, event_lng, v_lat, v_lng), 2)
                geocode_method = "postcode"

        if geocode_method == "none" and address:
            # No postcode found — geocode the street address via Nominatim
            coords = geocode_address(address)
            if coords:
                v_lat, v_lng = coords
                dist_km = round(haversine_km(event_lat, event_lng, v_lat, v_lng), 2)
                geocode_method = "address"
                logger.debug("Address geocode succeeded for '%s': %.2f km", name[:40], dist_km)

        if geocode_method == "none":
            logger.debug("No location resolved for '%s' — postcode and address both failed", name[:40])

        # ── Phone ─────────────────────────────────────────────────────────────
        phones = _PHONE_RE.findall(full_text)
        phone = phones[0].strip() if phones else ""

        # ── Price ─────────────────────────────────────────────────────────────
        prices = _PRICE_RE.findall(full_text)
        price_per_head = float(prices[0]) if prices else None

        # ── Dietary / cuisine ─────────────────────────────────────────────────
        specializations = [
            cat for cat in
            ["vegetarian", "vegan", "halal", "kosher", "gluten_free",
             "dairy-free", "nut-free"]
            if cat.replace("_", "-") in text_lower or cat in text_lower
        ]
        cuisine = _extract_cuisine_hint(text_lower)

        # ── Delivery ─────────────────────────────────────────────────────────
        # Only True if vendor explicitly says so — do NOT infer from distance
        delivery_keywords = ["delivery", "deliver to", "we deliver", "catering delivery",
                             "delivered to your", "delivery service", "deliver anywhere"]
        delivery_available = (
            any(kw in text_lower for kw in delivery_keywords)
            or url_info.get("is_delivery_platform", False)
        )

        # Infer vendor type from title/text
        vendor_type = "catering"
        hotel_keywords = ["hotel", "accommodation", "lodge", "inn", "b&b", "guest house",
                          "conference centre", "venue"]
        if any(kw in text_lower for kw in hotel_keywords):
            vendor_type = "hotel"

        return ScrapedVendor(
            name=name[:100],
            vendor_type=vendor_type,
            address=address,
            postcode=vendor_postcode,
            lat=v_lat,
            lng=v_lng,
            distance_km=dist_km,
            delivery_available=delivery_available,
            price_per_head=price_per_head,
            specializations=specializations,
            cuisine=cuisine,
            phone=phone,
            website=url,
            description=url_info.get("snippet", "")[:300],
            source="web_search",
        )

    except Exception as exc:
        logger.debug("Parse error for %s: %s", url, exc)
        return None


def _vendor_from_snippet(url_info: dict, event_lat: float, event_lng: float) -> Optional[ScrapedVendor]:
    """
    Build a ScrapedVendor directly from the DDG search result title+snippet.
    No HTTP request needed — fast and never blocked.
    Only usable when the snippet contains a UK postcode for geocoding.
    """
    title   = url_info.get("title", "")
    snippet = url_info.get("snippet", "")
    combined = f"{title} {snippet}"
    lower    = combined.lower()

    # Must have a meaningful name
    name = title.split("|")[0].split("–")[0].split("·")[0].split("-")[0].strip()
    if not name or len(name) < 3:
        return None

    # Must have a UK postcode in the snippet to be usable
    pc_matches = _UK_POSTCODE_RE.findall(combined)
    if not pc_matches:
        return None
    vendor_postcode = pc_matches[0].upper()

    coords = _try_geocode_postcode(vendor_postcode)
    if not coords:
        return None
    v_lat, v_lng = coords
    dist_km = round(haversine_km(event_lat, event_lng, v_lat, v_lng), 2)

    vendor_type = "catering"
    if any(kw in lower for kw in ["hotel", "inn", "lodge", "accommodation",
                                    "b&b", "guest house", "conference centre"]):
        vendor_type = "hotel"

    delivery_available = (
        any(kw in lower for kw in ["delivery", "takeaway", "deliver to"])
        or url_info.get("is_delivery_platform", False)
    )

    return ScrapedVendor(
        name=name[:100],
        vendor_type=vendor_type,
        postcode=vendor_postcode,
        lat=v_lat,
        lng=v_lng,
        distance_km=dist_km,
        delivery_available=delivery_available,
        cuisine=_extract_cuisine_hint(lower),
        website=url_info.get("url", ""),
        description=snippet[:300],
        source="web_snippet",
    )


def _fsa_food_establishments(lat: float, lng: float, radius_km: float) -> List[ScrapedVendor]:
    """
    UK Food Standards Agency (FSA) open API — lists all registered food businesses.
    Free, no API key, authoritative government data, covers every UK town.
    Docs: https://api.ratings.food.gov.uk/help
    """
    vendors: List[ScrapedVendor] = []
    try:
        resp = requests.get(
            "https://api.ratings.food.gov.uk/Establishments",
            params={
                "latitude":        lat,
                "longitude":       lng,
                "maxDistanceLimit": min(int(radius_km), 20),  # API caps at 20 km
                "pageSize":        100,
                "sortOptionKey":   "distance",
            },
            headers={"x-api-version": "2", "Accept": "application/json"},
            timeout=25,
        )
        if resp.status_code != 200:
            logger.warning("FSA API returned %s", resp.status_code)
            return []

        data = resp.json()
        for est in data.get("establishments", []):
            name = (est.get("BusinessName") or "").strip()
            if not name:
                continue

            postcode = (est.get("PostCode") or "").strip().upper()
            address  = ", ".join(filter(None, [
                est.get("AddressLine1", ""), est.get("AddressLine2", ""),
                est.get("AddressLine3", ""), est.get("AddressLine4", ""),
            ]))

            dist_km, v_lat, v_lng = 0.0, 0.0, 0.0
            if postcode:
                coords = _try_geocode_postcode(postcode)
                if coords:
                    v_lat, v_lng = coords
                    dist_km = round(haversine_km(lat, lng, v_lat, v_lng), 2)

            vendor_type = "catering"

            vendors.append(ScrapedVendor(
                name=name[:100],
                vendor_type=vendor_type,
                address=address,
                postcode=postcode,
                lat=v_lat, lng=v_lng,
                distance_km=dist_km,
                description=f"Business type: {est.get('BusinessType', '')}",
                source="fsa_api",
            ))

        logger.info("FSA API: %d food establishments within %.0f km", len(vendors), radius_km)
    except Exception as exc:
        logger.warning("FSA API failed: %s", exc)
    return vendors


def _scrape_yell_results(category: str, city: str, event_lat: float, event_lng: float) -> List[ScrapedVendor]:
    """
    Scrape Yell.com search results for a category in a city.
    Yell.com is a reliable UK business directory with static HTML listing pages.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    city_slug = city.lower().replace(" ", "-")
    url = f"https://www.yell.com/s/{category.replace(' ', '-')}-{city_slug}.html"
    vendors: List[ScrapedVendor] = []

    try:
        resp = httpx.get(url, timeout=20, headers=_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            logger.debug("Yell.com %s returned %s", url, resp.status_code)
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        # Yell listings are in <article> or div with class containing 'businessCapsule' or 'listing'
        cards = (
            soup.find_all("article", attrs={"class": lambda c: c and "business" in c.lower()})
            or soup.find_all("div", attrs={"class": lambda c: c and "businessCapsule" in (c or "")})
            or soup.find_all("div", attrs={"itemprop": "itemListElement"})
        )

        if not cards:
            # Fallback: any element with itemprop="name" that's a business name
            cards = soup.find_all(attrs={"itemtype": "http://schema.org/LocalBusiness"})

        for card in cards[:20]:
            name_el = (
                card.find(attrs={"itemprop": "name"})
                or card.find(["h2", "h3"])
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            card_text = card.get_text(" ", strip=True)
            pc_matches = _UK_POSTCODE_RE.findall(card_text)
            vendor_postcode = pc_matches[0].upper() if pc_matches else ""

            dist_km = 0.0
            v_lat, v_lng = 0.0, 0.0
            if vendor_postcode:
                coords = _try_geocode_postcode(vendor_postcode)
                if coords:
                    v_lat, v_lng = coords
                    dist_km = round(haversine_km(event_lat, event_lng, v_lat, v_lng), 2)

            phone_el = card.find(attrs={"itemprop": "telephone"})
            phone = phone_el.get_text(strip=True) if phone_el else ""

            url_el = card.find("a", href=True)
            vendor_url = url_el["href"] if url_el else ""
            if vendor_url and not vendor_url.startswith("http"):
                vendor_url = f"https://www.yell.com{vendor_url}"

            lower = card_text.lower()
            vendor_type = "hotel" if any(kw in lower for kw in ["hotel", "inn", "lodge", "accommodation"]) else "catering"

            vendors.append(ScrapedVendor(
                name=name[:100],
                vendor_type=vendor_type,
                postcode=vendor_postcode,
                lat=v_lat,
                lng=v_lng,
                distance_km=dist_km,
                cuisine=_extract_cuisine_hint(lower),
                phone=phone,
                website=vendor_url,
                description=card_text[:300],
                source="yell.com",
            ))

        logger.info("Yell.com '%s' in '%s': %d listings", category, city, len(vendors))
    except Exception as exc:
        logger.warning("Yell.com scrape failed for %s/%s: %s", category, city, exc)

    return vendors


def _search_and_scrape_vendors(
    config: EventScraperConfig, event_lat: float, event_lng: float
) -> List[ScrapedVendor]:
    """
    DDG search → extract vendors:
      1st pass: build vendor from snippet alone (fast, no HTTP, always works)
      2nd pass: full page scrape only for results that have no postcode in snippet
                AND are promising (hotel/catering domain, non-aggregator)
    """
    url_infos = _collect_vendor_urls(config)
    vendors: List[ScrapedVendor] = []
    needs_scrape: List[dict] = []

    for ui in url_infos:
        # Try snippet-first extraction
        v = _vendor_from_snippet(ui, event_lat, event_lng)
        if v:
            vendors.append(v)
        else:
            # No postcode in snippet — queue for full page scrape if domain looks useful
            domain = ui.get("domain", "")
            if domain not in _SKIP_DOMAINS and not any(
                s in ui.get("url", "") for s in ["/search?", "youtube.com", "reddit.com"]
            ):
                needs_scrape.append(ui)

    logger.info("Snippet extraction: %d vendors; queued %d for full scrape", len(vendors), len(needs_scrape))

    # Full page scrape for remaining URLs (capped to avoid long runtime)
    for ui in needs_scrape[:25]:
        v = _scrape_url(ui, event_lat, event_lng)
        if v:
            vendors.append(v)
        time.sleep(0.4)

    logger.info("Web search total: %d vendors from %d URLs", len(vendors), len(url_infos))
    return vendors


# ── OSM Overpass queries ──────────────────────────────────────────────────────

def _run_overpass(query: str, timeout_s: int = 120) -> list:
    try:
        resp = requests.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=timeout_s,
            headers={"User-Agent": "EventManagerApp/1.0"},
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])
    except Exception as exc:
        logger.warning("Overpass request failed: %s", exc)
        return []


def _overpass_nearby(lat: float, lng: float, radius_m: int, tags: List[str]) -> list:
    """
    Query Overpass for node+way+relation.  Large tag lists are split into
    batches of 5 to keep individual queries fast (avoids request timeouts).
    """
    all_elements: list = []
    batch_size = 5
    for i in range(0, len(tags), batch_size):
        batch = tags[i: i + batch_size]
        blocks = []
        for t in batch:
            blocks.append(f'  node[{t}](around:{radius_m},{lat},{lng});')
            blocks.append(f'  way[{t}](around:{radius_m},{lat},{lng});')
            blocks.append(f'  relation[{t}](around:{radius_m},{lat},{lng});')
        query = "[out:json][timeout:60];\n(\n" + "\n".join(blocks) + "\n);\nout center;"
        els = _run_overpass(query, timeout_s=70)
        all_elements.extend(els)
        if i + batch_size < len(tags):
            time.sleep(0.5)   # polite pause between batches
    return all_elements


def _element_to_vendor(
    elem: dict, event_lat: float, event_lng: float, vendor_type: str
) -> Optional[ScrapedVendor]:
    tags = elem.get("tags", {})
    name = tags.get("name", "").strip()
    if not name:
        return None

    # node → has lat/lon directly; way/relation → coordinates in "center" key
    center = elem.get("center") or {}
    lat  = float(elem.get("lat") or center.get("lat") or 0)
    lng  = float(elem.get("lon") or center.get("lon") or 0)
    if not lat and not lng:
        return None   # element has no coordinates at all — skip

    dist = haversine_km(event_lat, event_lng, lat, lng)

    specializations: List[str] = []
    cuisine = tags.get("cuisine", "")
    for cat, osm_vals in _DIET_TAG_MAP.items():
        diet_tag = tags.get(f"diet:{cat}", "")
        if diet_tag in ("yes", "only") or cuisine in osm_vals:
            specializations.append(cat)

    address_parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:city", ""),
    ]
    address = ", ".join(p for p in address_parts if p)

    # OSM restaurants are physical locations; delivery must come from their own tags
    delivery_tag = tags.get("delivery", tags.get("takeaway", ""))
    delivery_available = delivery_tag in ("yes", "only")

    return ScrapedVendor(
        name=name,
        vendor_type=vendor_type,
        address=address,
        postcode=tags.get("addr:postcode", ""),
        lat=lat,
        lng=lng,
        distance_km=round(dist, 2),
        delivery_available=delivery_available,
        specializations=specializations,
        cuisine=cuisine,
        phone=tags.get("phone", tags.get("contact:phone", "")),
        website=tags.get("website", tags.get("contact:website", "")),
        opening_hours=tags.get("opening_hours", ""),
        osm_id=str(elem.get("id", "")),
        source="overpass",
    )


# ── feedr.co Playwright scraper (optional) ────────────────────────────────────

def _scrape_feedr(lat: float, lng: float, attendees: int) -> List[ScrapedVendor]:
    """Scrape feedr.co — only runs if playwright + bs4 installed."""
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        logger.info("playwright/bs4 not installed — skipping feedr.co")
        return []

    url = (
        "https://feedr.co/en-gb/office-catering/vendors"
        f"?headCount={max(attendees, 1)}"
        f"&lat={lat}&lng={lng}"
        "&orderByDirection=asc&orderByProperty=distance"
        "&supplierType=catering"
    )

    vendors: List[ScrapedVendor] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        for card in soup.find_all("article"):
            name_el = card.find(["h2", "h3", "h4"])
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            text = card.get_text(" ", strip=True)
            vendors.append(ScrapedVendor(
                name=name,
                vendor_type="catering",
                lat=lat, lng=lng,
                distance_km=0.0,
                delivery_available=True,   # feedr.co is a delivery platform
                price_per_head=_extract_price(text),
                cuisine=_extract_cuisine_hint(text.lower()),
                source="feedr.co",
            ))
        logger.info("feedr.co: %d cards", len(vendors))
    except Exception as exc:
        logger.warning("feedr.co scrape failed: %s", exc)

    return vendors


# ── Text helpers ──────────────────────────────────────────────────────────────

def _extract_price(text: str) -> Optional[float]:
    match = re.search(r"£(\d+(?:\.\d{1,2})?)", text)
    return float(match.group(1)) if match else None


def _extract_cuisine_hint(text_lower: str) -> str:
    # Specific chain detection first
    chains = {
        "mcdonald": "fast food", "kfc": "fast food", "subway": "sandwiches",
        "pizza hut": "pizza", "domino": "pizza", "papa john": "pizza",
        "nando": "peri-peri chicken", "wagamama": "asian", "pret": "sandwiches",
        "greggs": "bakery", "costa": "cafe", "starbucks": "cafe",
        "burger king": "fast food", "five guys": "burgers",
        "leon": "healthy fast food", "itsu": "sushi", "wasabi": "japanese",
        "yo sushi": "sushi", "just eat": "delivery", "deliveroo": "delivery",
    }
    for chain, cuisine in chains.items():
        if chain in text_lower:
            return cuisine

    # Cuisine types
    for kw in ["italian", "indian", "chinese", "japanese", "thai", "mexican",
               "british", "american", "halal", "vegan", "vegetarian", "mediterranean",
               "caribbean", "african", "korean", "middle eastern", "greek", "spanish",
               "turkish", "lebanese", "persian", "bangladeshi", "pakistani",
               "pizza", "burger", "sushi", "tapas", "dim sum", "bbq", "barbecue",
               "seafood", "fish and chips", "pie", "sandwich", "wrap", "salad"]:
        if kw in text_lower:
            return kw
    return ""


# ── Main orchestrator ─────────────────────────────────────────────────────────

def get_nearby_towns(postcode: str, limit: int = 8) -> List[dict]:
    """
    Return nearby towns/districts when no vendors are found in the event area.
    Uses postcodes.io /outcodes/{outcode}/nearest (free, no key).

    Returns list of {town, outcode, distance_km, postcode_example}
    """
    try:
        outcode = postcode.replace(" ", "").upper()[:-3]  # strip inward code
        resp = requests.get(
            f"https://api.postcodes.io/outcodes/{outcode}/nearest",
            params={"limit": limit + 1, "radius": 30000},
            timeout=10,
            headers={"User-Agent": "EventManagerApp/1.0"},
        )
        data = resp.json()
        towns = []
        for r in (data.get("result") or []):
            oc = r.get("outcode", "")
            if oc == outcode:
                continue   # skip the event postcode itself
            districts = r.get("admin_district") or []
            town = districts[0] if districts else oc
            dist_m = r.get("distance", 0)
            towns.append({
                "town":            town,
                "outcode":         oc,
                "distance_km":     round(dist_m / 1000, 1),
                "postcode_example": f"{oc} 1AA",   # safe example for display
            })
        return towns[:limit]
    except Exception as exc:
        logger.warning("Nearby towns lookup failed: %s", exc)
        return []


def run_event_scrape(config: EventScraperConfig) -> List[ScrapedVendor]:
    logger.info(
        "Event scrape: postcode=%s radius=%.1fkm food=%s hotel=%s",
        config.postcode, config.radius_km, config.food_required, config.hotel_required,
    )

    lat, lng = postcode_to_coords(config.postcode)
    logger.info("Geocoded %s → (%.5f, %.5f)", config.postcode, lat, lng)

    radius_m = int(min(config.radius_km, 100.0) * 1000)
    vendors: List[ScrapedVendor] = []

    # ── 1. FSA food business API (UK gov, always works, no rate limits) ──────
    if config.food_required:
        fsa_vendors = _fsa_food_establishments(lat, lng, config.radius_km)
        vendors.extend(fsa_vendors)

    # ── 2. OSM Overpass — geo-precise backbone ────────────────────────────────
    if config.food_required:
        # Run in batches (batching is inside _overpass_nearby now)
        elements = _overpass_nearby(lat, lng, radius_m, _CATERING_TAGS)
        for elem in elements:
            v = _element_to_vendor(elem, lat, lng, "catering")
            if v:
                vendors.append(v)
        osm_food_count = sum(1 for v in vendors if v.source == "overpass" and v.vendor_type == "catering")
        logger.info("OSM catering: %d elements found", osm_food_count)
        vendors.extend(_scrape_feedr(lat, lng, config.attendees))

    if config.hotel_required:
        h_elements = _overpass_nearby(lat, lng, radius_m, _HOTEL_TAGS)
        for elem in h_elements:
            v = _element_to_vendor(elem, lat, lng, "hotel")
            if v:
                vendors.append(v)
        osm_hotel_count = sum(1 for v in vendors if v.vendor_type == "hotel")
        logger.info("OSM hotels: %d elements found", osm_hotel_count)

    # ── 3. DuckDuckGo web search (supplementary, may be rate-limited) ─────────
    web_vendors = _search_and_scrape_vendors(config, lat, lng)
    vendors.extend(web_vendors)
    logger.info("Web search: %d vendors added", len(web_vendors))

    vendors.sort(key=lambda v: (
        v.delivery_available,
        v.distance_km if v.distance_km > 0 else 999,
    ))

    logger.info("Scrape complete: %d total vendors (pre-filter)", len(vendors))
    return vendors
