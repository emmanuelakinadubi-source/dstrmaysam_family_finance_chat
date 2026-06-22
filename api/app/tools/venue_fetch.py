import logging
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_MAP = {
    "id": ["id", "venue_id", "slug", "identifier"],
    "name": ["name", "venue_name", "title"],
    "description": ["description", "about", "overview", "summary", "details"],
    "city": ["city", "location", "town", "region", "area"],
    "max_capacity": ["max_capacity", "capacity", "max_guests", "max_attendees", "maximum_capacity"],
    "min_capacity": ["min_capacity", "min_guests", "min_attendees", "minimum_capacity"],
    "min_price": ["min_price", "price_from", "starting_price", "minimum_price"],
    "max_price": ["max_price", "price_to", "maximum_price"],
    "images": ["images", "photos", "gallery", "image_urls", "pictures"],
    "features": ["features", "amenities", "facilities", "tags", "highlights"],
    "address": ["address", "full_address", "street_address", "location_address"],
}


def _get(obj: Dict, keys: List[str], default=None):
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return default


def _extract_image_url(img) -> str:
    if isinstance(img, str):
        return img.strip()
    if isinstance(img, dict):
        for key in ("url", "src", "href", "image_url", "path", "uri", "link"):
            if img.get(key) and isinstance(img[key], str):
                return img[key].strip()
    return ""


def _bool_field(*sources: Dict, keys: List[str]) -> Optional[bool]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for k in keys:
            v = source.get(k)
            if v is None:
                continue
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "yes", "1", "available", "yes, available")
            if isinstance(v, (int, float)):
                return bool(v)
    return None


def _str_field(*sources: Dict, keys: List[str], default: str = "") -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for k in keys:
            v = source.get(k)
            if v and isinstance(v, str):
                return v.strip()
    return default


def _int_field(*sources: Dict, keys: List[str]) -> Optional[int]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for k in keys:
            v = source.get(k)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    continue
    return None


def _list_field(*sources: Dict, keys: List[str]) -> List[str]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for k in keys:
            v = source.get(k)
            if v is None:
                continue
            if isinstance(v, list):
                return [str(i).strip() for i in v if i]
            if isinstance(v, str) and v.strip():
                return [s.strip() for s in v.split(",") if s.strip()]
    return []


def normalize_venue(raw: Dict) -> Dict[str, Any]:
    # Nested capacity
    cap_raw = raw.get("capacity", {})
    if isinstance(cap_raw, dict):
        max_cap = cap_raw.get("max", cap_raw.get("maximum", 0))
        min_cap = cap_raw.get("min", cap_raw.get("minimum", 0))
    else:
        max_cap = _get(raw, _KEY_MAP["max_capacity"], cap_raw or 0)
        min_cap = _get(raw, _KEY_MAP["min_capacity"], 0)

    # Nested pricing
    price_raw = raw.get("pricing", raw.get("price", {}))
    if isinstance(price_raw, dict):
        min_price = price_raw.get("min", price_raw.get("from", price_raw.get("minimum", 0)))
        max_price = price_raw.get("max", price_raw.get("to", price_raw.get("maximum", 0)))
    else:
        min_price = _get(raw, _KEY_MAP["min_price"], price_raw or 0)
        max_price = _get(raw, _KEY_MAP["max_price"], 0)

    images = _get(raw, _KEY_MAP["images"], [])
    if isinstance(images, str):
        images = [images]
    images = [_extract_image_url(img) for img in images if _extract_image_url(img)]

    features = _get(raw, _KEY_MAP["features"], [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split(",") if f.strip()]

    # Pull nested facility/detail objects for enrichment
    facilities = raw.get("facilities", raw.get("amenities", raw.get("information", raw.get("details", {}))))
    if not isinstance(facilities, dict):
        facilities = {}

    event_types = _list_field(raw, facilities, keys=[
        "event_types", "events", "suitable_for", "suitable", "uses", "type_of_events"
    ])

    return {
        "venue_id": str(_get(raw, _KEY_MAP["id"], "unknown")),
        "name": _get(raw, _KEY_MAP["name"], "Unknown Venue"),
        "description": _get(raw, _KEY_MAP["description"], ""),
        "city": _get(raw, _KEY_MAP["city"], ""),
        "postcode": _str_field(raw, facilities, keys=["postcode", "post_code", "zip", "zipcode"]),
        "max_capacity": int(max_cap) if max_cap else 0,
        "min_capacity": int(min_cap) if min_cap else 0,
        "min_price": float(min_price) if min_price else 0.0,
        "max_price": float(max_price) if max_price else 0.0,
        "images": images[:3] if images else [],
        "features": features if isinstance(features, list) else [],
        "address": _get(raw, _KEY_MAP["address"], ""),
        "event_types": event_types,
        "venue_url": _str_field(raw, facilities, keys=["url", "website", "link", "venue_url", "website_url"]),
        # Operational facilities
        "parking": _bool_field(raw, facilities, keys=["parking", "has_parking", "car_park"]),
        "nearest_parking": _str_field(raw, facilities, keys=["nearest_parking", "nearby_parking", "parking_facility"]),
        "public_transport": _str_field(raw, facilities, keys=["public_transport", "transport", "getting_here"]),
        "nearest_train": _str_field(raw, facilities, keys=["nearest_train", "train_station", "nearest_train_station"]),
        "nearest_underground": _str_field(raw, facilities, keys=["nearest_tube", "underground", "nearest_underground", "tube"]),
        "wheelchair_access": _bool_field(raw, facilities, keys=["wheelchair_access", "disabled_access", "accessibility", "wheelchair"]),
        "wifi": _bool_field(raw, facilities, keys=["wifi", "wi_fi", "wireless", "internet"]),
        "av_equipment": _bool_field(raw, facilities, keys=["av_equipment", "av", "audio_visual", "projector", "screen"]),
        "hybrid_events": _bool_field(raw, facilities, keys=["hybrid", "hybrid_events", "virtual", "virtual_events"]),
        "live_streaming": _bool_field(raw, facilities, keys=["live_streaming", "streaming", "broadcast"]),
        "catering": _bool_field(raw, facilities, keys=["catering", "food", "catering_available", "in_house_catering"]),
        "alcohol_license": _bool_field(raw, facilities, keys=["alcohol_license", "bar", "alcohol", "licensed", "bar_available"]),
        "accommodation": _bool_field(raw, facilities, keys=["accommodation", "rooms", "hotel", "bedrooms", "overnight"]),
        "meeting_rooms": _int_field(raw, facilities, keys=["meeting_rooms", "breakout_rooms", "syndicate_rooms"]),
        "outdoor_space": _bool_field(raw, facilities, keys=["outdoor", "garden", "terrace", "outdoor_space", "courtyard"]),
        "sustainability": _str_field(raw, facilities, keys=["sustainability", "green", "eco", "carbon_neutral", "environmental"]),
        "response_rate": _str_field(raw, keys=["response_rate", "responseRate", "response_percentage"]),
        "response_time": _str_field(raw, keys=["response_time", "responseTime", "avg_response_time"]),
    }


def fetch_venues() -> List[Dict[str, Any]]:
    try:
        resp = requests.get(
            settings.canvas_api_url,
            timeout=30,
            headers={"Accept": "application/json", "User-Agent": "CorporateEventApp/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            raw_venues = data
        elif isinstance(data, dict):
            for key in ("data", "venues", "results", "items"):
                if key in data and isinstance(data[key], list):
                    raw_venues = data[key]
                    break
            else:
                raw_venues = [data]
        else:
            raw_venues = []

        venues = [normalize_venue(v) for v in raw_venues]
        logger.info("Fetched %d venues from Canvas API", len(venues))
        return venues

    except requests.exceptions.RequestException as exc:
        logger.error("Canvas API request failed: %s", exc)
        return []
