import requests
r = requests.get(
    "https://api.ratings.food.gov.uk/Establishments",
    params={"latitude": 51.7333, "longitude": 0.4658,
            "maxDistanceLimit": 5, "pageSize": 10, "sortOptionKey": "distance"},
    headers={"x-api-version": "2", "Accept": "application/json"},
    timeout=20,
)
d = r.json()
ests = d.get("establishments", [])
print(f"FSA API: status={r.status_code} | {len(ests)} establishments")
for e in ests[:5]:
    print(f"  {e.get('BusinessName')} | {e.get('BusinessType')} | {e.get('PostCode')}")
