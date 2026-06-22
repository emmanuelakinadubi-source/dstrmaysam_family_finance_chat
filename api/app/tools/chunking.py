from typing import Any, Dict, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


def _bool_to_str(v: Optional[bool]) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return ""


def _venue_to_text(venue: Dict[str, Any]) -> str:
    features = ", ".join(venue.get("features", []))
    event_types = ", ".join(venue.get("event_types", []))

    lines = [
        f"Venue Name: {venue['name']}",
        f"City: {venue.get('city', 'Unknown')}",
        f"Postcode: {venue.get('postcode', '')}",
        f"Description: {venue.get('description', '')}",
        f"Maximum Capacity: {venue.get('max_capacity', 0)} guests",
        f"Minimum Capacity: {venue.get('min_capacity', 0)} guests",
        f"Price Range: £{venue.get('min_price', 0):,.0f} - £{venue.get('max_price', 0):,.0f}",
        f"Features: {features}",
        f"Event Types: {event_types}",
        f"Address: {venue.get('address', '')}",
    ]

    # Operational details
    for label, key in [
        ("Parking", "parking"), ("WiFi", "wifi"), ("AV Equipment", "av_equipment"),
        ("Catering", "catering"), ("Wheelchair Access", "wheelchair_access"),
        ("Hybrid Events", "hybrid_events"), ("Outdoor Space", "outdoor_space"),
        ("Alcohol License", "alcohol_license"), ("Accommodation", "accommodation"),
    ]:
        val = _bool_to_str(venue.get(key))
        if val:
            lines.append(f"{label}: {val}")

    for label, key in [
        ("Nearest Train Station", "nearest_train"),
        ("Nearest Underground", "nearest_underground"),
        ("Public Transport", "public_transport"),
        ("Sustainability", "sustainability"),
    ]:
        val = venue.get(key, "")
        if val:
            lines.append(f"{label}: {val}")

    return "\n".join(lines)


def chunk_venue(venue: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = _venue_to_text(venue)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(text)

    def _safe_bool(v) -> str:
        if v is True:
            return "true"
        if v is False:
            return "false"
        return ""

    metadata = {
        "venue_id": venue["venue_id"],
        "venue_name": venue["name"],
        "city": venue.get("city", ""),
        "postcode": venue.get("postcode", ""),
        "capacity": str(venue.get("max_capacity", 0)),
        "min_price": str(venue.get("min_price", 0)),
        "max_price": str(venue.get("max_price", 0)),
        "images": ",".join(str(i) for i in venue.get("images", [])[:1] if i),
        "features": ",".join(venue.get("features", [])[:10]),
        "event_types": ",".join(venue.get("event_types", [])[:10]),
        "venue_url": venue.get("venue_url", ""),
        "source": "Canvas API",
        # Operational booleans stored as strings
        "parking": _safe_bool(venue.get("parking")),
        "wifi": _safe_bool(venue.get("wifi")),
        "av_equipment": _safe_bool(venue.get("av_equipment")),
        "catering": _safe_bool(venue.get("catering")),
        "wheelchair_access": _safe_bool(venue.get("wheelchair_access")),
        "hybrid_events": _safe_bool(venue.get("hybrid_events")),
        "outdoor_space": _safe_bool(venue.get("outdoor_space")),
        "alcohol_license": _safe_bool(venue.get("alcohol_license")),
        "accommodation": _safe_bool(venue.get("accommodation")),
        "nearest_train": venue.get("nearest_train", ""),
        "nearest_underground": venue.get("nearest_underground", ""),
        "nearest_parking": venue.get("nearest_parking", ""),
        "response_rate": venue.get("response_rate", ""),
        "response_time": venue.get("response_time", ""),
        "sustainability": venue.get("sustainability", ""),
    }

    # Remove empty-string values (ChromaDB metadata must not have None)
    metadata = {k: v for k, v in metadata.items() if v is not None}

    return [
        {"text": chunk, "metadata": metadata, "id": f"{venue['venue_id']}_{i}"}
        for i, chunk in enumerate(chunks)
    ]


def chunk_venues(venues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_chunks: List[Dict[str, Any]] = []
    for venue in venues:
        all_chunks.extend(chunk_venue(venue))
    return all_chunks
