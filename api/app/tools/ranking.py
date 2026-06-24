from typing import Any, Dict, List, Optional

from app.schemas.event import EventRequirements


def _capacity_component(metadata: Dict, requirements: EventRequirements, relaxed: bool = False) -> float:
    """40% weight — returns 0.0–1.0"""
    try:
        capacity = int(metadata.get("capacity") or 0)
        attendees = requirements.attendees
        if attendees <= 0:
            return 0.80
        if capacity <= 0:
            return 0.50
        ratio = capacity / attendees
        if ratio >= 1.0:
            return 1.00
        if ratio >= 0.90:
            return 0.85
        if ratio >= (0.70 if relaxed else 0.80):
            return 0.65 if not relaxed else 0.80
        if relaxed and ratio >= 0.50:
            return 0.40
    except (TypeError, ValueError):
        return 0.50
    return 0.0


def _budget_component(metadata: Dict, requirements: EventRequirements, relaxed: bool = False) -> float:
    """20% weight — returns 0.0–1.0"""
    try:
        min_price = float(metadata.get("min_price") or 0)
        req_max = requirements.max_budget
        if req_max <= 0:
            return 0.80
        ceiling = req_max * (1.50 if relaxed else 1.0)
        if min_price <= req_max:
            return 1.00
        if min_price <= req_max * 1.10:
            return 0.85
        if min_price <= req_max * 1.20:
            return 0.70
        if relaxed and min_price <= ceiling:
            return 0.50
    except (TypeError, ValueError):
        return 0.50
    return 0.0


def _location_component(metadata: Dict, requirements: EventRequirements) -> float:
    """15% weight — returns 0.0–1.0"""
    if not requirements.city:
        return 0.80
    venue_city = (metadata.get("city") or "").lower()
    req_city = requirements.city.lower()
    if req_city in venue_city or venue_city in req_city:
        return 1.00
    if any(word in venue_city for word in req_city.split() if len(word) > 2):
        return 0.70
    return 0.0


def city_matches(metadata: Dict, requirements: EventRequirements) -> bool:
    """Hard location guard — False means this venue is in the wrong city/region entirely."""
    if not requirements.city:
        return True   # no location constraint → all cities pass
    venue_city = (metadata.get("city") or "").lower()
    req_city = requirements.city.lower()
    if not venue_city:
        return False  # no city on venue → reject when event has a city
    if req_city in venue_city or venue_city in req_city:
        return True
    # Allow county / region synonyms (e.g. "Essex" matches "Chelmsford")
    if any(word in venue_city for word in req_city.split() if len(word) > 2):
        return True
    return False


def _event_type_component(metadata: Dict, requirements: EventRequirements) -> float:
    """10% weight — returns 0.0–1.0"""
    venue_types = (metadata.get("event_types") or "").lower()
    if not venue_types:
        return 0.50
    if requirements.additional_requirements:
        for req in requirements.additional_requirements:
            words = req.lower().split()
            if any(w in venue_types for w in words if len(w) > 3):
                return 1.00
    return 0.60


def _feature_component(metadata: Dict, requirements: EventRequirements) -> float:
    """10% weight — returns 0.0–1.0"""
    if not requirements.additional_requirements:
        return 0.80

    features_text = " ".join([
        (metadata.get("features") or ""),
        (metadata.get("venue_name") or ""),
        (metadata.get("event_types") or ""),
    ]).lower()

    feature_flags = {
        "parking": _meta_bool(metadata, ["parking"]),
        "wifi": _meta_bool(metadata, ["wifi"]),
        "av": _meta_bool(metadata, ["av_equipment"]),
        "catering": _meta_bool(metadata, ["catering"]),
        "wheelchair": _meta_bool(metadata, ["wheelchair_access"]),
        "hybrid": _meta_bool(metadata, ["hybrid_events"]),
        "outdoor": _meta_bool(metadata, ["outdoor_space"]),
    }

    matched = 0
    total = len(requirements.additional_requirements)
    for req in requirements.additional_requirements:
        req_lower = req.lower()
        found = False
        for keyword, available in feature_flags.items():
            if keyword in req_lower and available:
                matched += 1
                found = True
                break
        if not found and req_lower in features_text:
            matched += 1

    return matched / total if total > 0 else 0.80


def _business_component(metadata: Dict) -> float:
    """5% weight — returns 0.0–1.0"""
    response_rate = (metadata.get("response_rate") or "").replace("%", "").strip()
    if response_rate:
        try:
            rate = float(response_rate)
            return min(rate / 100.0, 1.0)
        except ValueError:
            pass
    return 0.60


def _meta_bool(metadata: Dict, keys: List[str]) -> bool:
    for k in keys:
        v = metadata.get(k)
        if v is None:
            continue
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "1")
    return False


def score_venue(
    venue_data: Dict[str, Any],
    requirements: EventRequirements,
    relaxed: bool = False,
) -> float:
    """Score 0–100 using weighted formula: 40/20/15/10/10/5."""
    meta = venue_data.get("metadata", {})

    cap = _capacity_component(meta, requirements, relaxed)
    bud = _budget_component(meta, requirements, relaxed)
    loc = _location_component(meta, requirements)
    evt = _event_type_component(meta, requirements)
    feat = _feature_component(meta, requirements)
    biz = _business_component(meta)

    weighted = cap * 0.40 + bud * 0.20 + loc * 0.15 + evt * 0.10 + feat * 0.10 + biz * 0.05

    venue_data["score_breakdown"] = {
        "capacity_score": round(cap * 100, 1),
        "budget_score": round(bud * 100, 1),
        "location_score": round(loc * 100, 1),
        "event_type_score": round(evt * 100, 1),
        "feature_score": round(feat * 100, 1),
        "business_score": round(biz * 100, 1),
    }

    return min(round(weighted * 100, 1), 100.0)


def rank_venues(
    chunks: List[Dict[str, Any]],
    requirements: EventRequirements,
    relaxed: bool = False,
) -> List[Dict[str, Any]]:
    best_per_venue: Dict[str, Dict] = {}
    for chunk in chunks:
        vid = chunk.get("metadata", {}).get("venue_id", "")
        if vid not in best_per_venue or chunk.get("relevance_score", 0) > best_per_venue[vid].get("relevance_score", 0):
            best_per_venue[vid] = chunk

    unique = list(best_per_venue.values())

    # Hard location guard — drop venues that are not in the requested city.
    # We do this before scoring so wrong-city venues never appear regardless of
    # how good their capacity/budget scores are.
    city_filtered = [v for v in unique if city_matches(v.get("metadata", {}), requirements)]

    for v in city_filtered:
        v["match_score"] = score_venue(v, requirements, relaxed=relaxed)

    return sorted(city_filtered, key=lambda v: v["match_score"], reverse=True)
