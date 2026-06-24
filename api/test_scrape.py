"""Quick diagnostic — run inside the API container."""
import sys, requests, json, logging
logging.basicConfig(level=logging.DEBUG)

# ── 1. Overpass reachability ───────────────────────────────────────────────────
QUERY = '[out:json][timeout:30];(node["tourism"="hotel"](around:10000,51.7333,0.4658);way["tourism"="hotel"](around:10000,51.7333,0.4658););out center;'
try:
    r = requests.post("https://overpass-api.de/api/interpreter",
                      data={"data": QUERY}, timeout=35,
                      headers={"User-Agent": "EventDiag/1.0"})
    els = r.json().get("elements", [])
    print(f"\n[OVERPASS] {len(els)} hotels returned")
    for e in els[:5]:
        c = e.get("center") or {}
        lat = e.get("lat") or c.get("lat")
        lon = e.get("lon") or c.get("lon")
        print(f"  {e['type']} | {e.get('tags',{}).get('name','?')} | {lat},{lon}")
except Exception as ex:
    print(f"[OVERPASS] FAILED: {ex}")

# ── 2. Pipeline trace on a known hotel element ────────────────────────────────
print("\n[PIPELINE] tracing location guardrail...")
sys.path.insert(0, "/app")
from app.modules.vendors.smart_scraper import EventScraperConfig, haversine_km, _element_to_vendor, postcode_to_coords
from app.modules.vendors.vendor_pipeline import _location_matches_event, _postcode_area, _postcode_outward

config = EventScraperConfig(
    postcode="CM1 6GQ", city="Chelmsford",
    attendees=120, total_budget=28500, radius_km=20,
    food_required=True, hotel_required=True,
)
try:
    elat, elng = postcode_to_coords("CM1 6GQ")
    print(f"Event coords: {elat}, {elng}")
except Exception as ex:
    print(f"Postcode geocode failed: {ex}")
    elat, elng = 51.7333, 0.4658

# Simulate a Premier Inn way element (as returned by Overpass with out center)
fake_way = {
    "type": "way", "id": 999,
    "center": {"lat": 51.735, "lon": 0.462},
    "tags": {"name": "Premier Inn (Springfield)", "tourism": "hotel"}
}
v = _element_to_vendor(fake_way, elat, elng, "hotel")
if v:
    print(f"Vendor built: {v.name} | distance={v.distance_km}km | postcode={v.postcode}")
    ok, reason = _location_matches_event(v, config)
    print(f"Guardrail: passes={ok} | reason={reason}")
else:
    print("_element_to_vendor returned None for way element!")

# Simulate a node element (old format)
fake_node = {
    "type": "node", "id": 888,
    "lat": 51.734, "lon": 0.471,
    "tags": {"name": "Travelodge Chelmsford", "tourism": "hotel"}
}
v2 = _element_to_vendor(fake_node, elat, elng, "hotel")
if v2:
    print(f"Node vendor: {v2.name} | distance={v2.distance_km}km")
    ok2, reason2 = _location_matches_event(v2, config)
    print(f"Guardrail: passes={ok2} | reason={reason2}")
else:
    print("_element_to_vendor returned None for node element!")

# ── 3. Yell.com reachability ──────────────────────────────────────────────────
print("\n[YELL] testing direct HTTP...")
try:
    yr = requests.get("https://www.yell.com/s/hotels-chelmsford.html",
                      timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
    print(f"Status: {yr.status_code} | size: {len(yr.text)} bytes")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(yr.text, "html.parser")
    cards = soup.find_all(attrs={"itemtype": "http://schema.org/LocalBusiness"})
    print(f"Schema.org LocalBusiness cards: {len(cards)}")
    for c in cards[:3]:
        n = c.find(attrs={"itemprop": "name"})
        print(f"  {n.get_text(strip=True) if n else '?'}")
except Exception as ex:
    print(f"Yell.com FAILED: {ex}")

print("\n[DONE]")
