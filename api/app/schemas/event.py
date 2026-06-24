from pydantic import BaseModel
from typing import Dict, List, Optional


class EventRequirements(BaseModel):
    event_date: Optional[str] = ""
    event_time: Optional[str] = ""
    city: Optional[str] = ""
    postcode: Optional[str] = None          # UK postcode — drives proximity vendor search
    radius_km: float = 5.0                  # search radius for nearby vendors / hotels
    food_required: bool = False
    food_categories: List[str] = []         # e.g. ["vegetarian", "halal", "vegan"]
    hotel_required: bool = False
    min_budget: float = 0.0
    max_budget: float = 0.0
    attendees: int = 0
    additional_requirements: List[str] = []


class ScoreBreakdown(BaseModel):
    capacity_score: float = 0.0
    budget_score: float = 0.0
    location_score: float = 0.0
    event_type_score: float = 0.0
    feature_score: float = 0.0
    business_score: float = 0.0


class VenueCard(BaseModel):
    venue_id: str
    venue_name: str
    venue_image: Optional[str] = ""
    city: str
    postcode: Optional[str] = ""
    capacity: str
    budget_compatibility: str
    venue_description: str
    venue_features: List[str] = []
    event_types: List[str] = []
    venue_url: Optional[str] = ""
    match_score: float
    score_breakdown: Optional[ScoreBreakdown] = None
    recommendation_reason: str
    is_fallback: bool = False
    # Operational details
    parking: Optional[bool] = None
    nearest_parking: Optional[str] = ""
    public_transport: Optional[str] = ""
    nearest_train: Optional[str] = ""
    nearest_underground: Optional[str] = ""
    wheelchair_access: Optional[bool] = None
    wifi: Optional[bool] = None
    av_equipment: Optional[bool] = None
    hybrid_events: Optional[bool] = None
    live_streaming: Optional[bool] = None
    catering: Optional[bool] = None
    alcohol_license: Optional[bool] = None
    accommodation: Optional[bool] = None
    meeting_rooms: Optional[int] = None
    outdoor_space: Optional[bool] = None
    sustainability: Optional[str] = ""
    response_rate: Optional[str] = ""
    response_time: Optional[str] = ""


class RecommendationSummary(BaseModel):
    total_venues: int
    best_venue: str
    budget_analysis: str
    capacity_analysis: str
    key_recommendations: List[str]


class EventUploadResponse(BaseModel):
    event_id: Optional[str] = None
    event_requirements: EventRequirements
    recommended_venues: List[VenueCard]
    summary: RecommendationSummary
    agent_response: Optional[str] = ""
    event_collection: Optional[str] = "event_management"


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    knowledge_source: str = "venue_master"
    history: List[ChatMessage] = []
    event_context: Optional[str] = None   # Injected draft summary for the agent


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
    knowledge_source: str = "venue_master"


class IndexingMetadata(BaseModel):
    last_indexed_at: Optional[str] = None
    total_venues: int = 0
    new_venues: int = 0
    updated_venues: int = 0
    removed_venues: int = 0
    total_chunks: int = 0
    status: str = "not_indexed"
