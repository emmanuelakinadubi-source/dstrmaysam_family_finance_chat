"""
LangChain tool: search locally scraped vendor intelligence from ChromaDB.

The chat agent calls this when the user asks about caterers or hotels
near the event postcode that were found via the smart scraper.
"""
from langchain_core.tools import tool


@tool
def search_nearby_vendors(
    query: str,
    vendor_type: str = "",
    event_id: str = "",
) -> str:
    """
    Search scraped caterers and hotels near the event location.

    Use this tool when the user asks about:
    - Food vendors, caterers, restaurants near the event
    - Hotels or accommodation near the event postcode
    - Which vendors fit the budget or dietary requirements
    - Distance to vendors from the venue

    Args:
        query: Natural language search query (e.g. "halal caterers within budget")
        vendor_type: Optional filter — "catering" or "hotel" (leave empty for both)
        event_id: Optional — restrict to vendors scraped for a specific event

    Returns a formatted list of matching vendors with distance, price, and specializations.
    """
    from app.modules.vendors.vendor_indexer import search_vendor_intel

    results = search_vendor_intel(
        query=query,
        vendor_type=vendor_type or None,
        event_id=event_id or None,
        k=8,
    )

    if not results:
        return (
            "No nearby vendor data found. "
            "Ask the user to run 'Find Local Vendors' for their event first, "
            "or widen the search radius."
        )

    lines = [f"Found {len(results)} nearby vendors matching '{query}':\n"]
    for i, r in enumerate(results, 1):
        m = r["metadata"]
        dist = f"{m.get('distance_km', 0):.1f} km away" if m.get("distance_km") else ""
        price = f"£{m.get('price_per_head', 0):.0f}/head" if m.get("price_per_head") else ""
        specs = m.get("specializations", "")
        specs_str = f" | Dietary: {specs}" if specs else ""
        cuisine = f" | {m.get('cuisine')}" if m.get("cuisine") else ""

        lines.append(
            f"{i}. **{m.get('name', 'Unknown')}** "
            f"({m.get('vendor_type', '').title()})"
            f"{(' — ' + dist) if dist else ''}"
            f"{(' — ' + price) if price else ''}"
            f"{cuisine}{specs_str}"
        )
        # Include the full text for context
        lines.append(f"   {r['content'][:200]}…\n")

    return "\n".join(lines)
