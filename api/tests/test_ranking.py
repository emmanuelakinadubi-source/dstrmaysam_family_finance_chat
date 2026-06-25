"""
Unit tests for app/tools/ranking.py

Tests the venue scoring model and location guardrail.
No external services required — all inputs are plain dicts.
"""
import pytest
from app.tools.ranking import (
    city_matches,
    score_venue,
    rank_venues,
    _capacity_component,
    _budget_component,
    _location_component,
)
from app.schemas.event import EventRequirements


def _make_venue(venue_id="v1", city="London", capacity=200, min_price=5000):
    return {
        "metadata": {
            "venue_id": venue_id,
            "venue_name": f"Test Venue {venue_id}",
            "city": city,
            "capacity": str(capacity),
            "min_price": str(min_price),
            "event_types": "conference",
            "features": "AV, parking",
            "parking": "true",
            "wifi": "true",
            "av_equipment": "true",
            "response_rate": "90",
        },
        "relevance_score": 0.9,
    }


def _make_reqs(**kwargs) -> EventRequirements:
    defaults = dict(city="London", attendees=150, max_budget=10000, min_budget=5000)
    defaults.update(kwargs)
    return EventRequirements(**defaults)


# ── city_matches ──────────────────────────────────────────────────────────────

class TestCityMatches:
    def test_exact_city_match(self):
        assert city_matches({"city": "London"}, _make_reqs(city="London")) is True

    def test_case_insensitive_match(self):
        assert city_matches({"city": "london"}, _make_reqs(city="London")) is True

    def test_substring_match(self):
        assert city_matches({"city": "Greater London"}, _make_reqs(city="London")) is True

    def test_wrong_city_rejected(self):
        assert city_matches({"city": "Manchester"}, _make_reqs(city="London")) is False

    def test_no_city_requirement_passes_all(self):
        assert city_matches({"city": "Manchester"}, _make_reqs(city="")) is True

    def test_empty_venue_city_rejected_when_event_has_city(self):
        assert city_matches({"city": ""}, _make_reqs(city="London")) is False

    def test_chelmsford_not_matched_by_london(self):
        assert city_matches({"city": "Chelmsford"}, _make_reqs(city="London")) is False


# ── score_venue ───────────────────────────────────────────────────────────────

class TestScoreVenue:
    def test_score_is_between_0_and_100(self):
        venue = _make_venue()
        reqs = _make_reqs()
        score = score_venue(venue, reqs)
        assert 0.0 <= score <= 100.0

    def test_perfect_venue_scores_high(self):
        venue = _make_venue(city="London", capacity=200, min_price=8000)
        reqs = _make_reqs(city="London", attendees=150, max_budget=10000)
        score = score_venue(venue, reqs)
        assert score >= 70.0

    def test_undersized_venue_scores_low(self):
        # capacity=0 (40% weight) leaves a max of 60 from the other components.
        # With good budget/location/features the realistic floor is ~53-54.
        venue = _make_venue(capacity=10)
        reqs = _make_reqs(attendees=500)
        score = score_venue(venue, reqs)
        assert score < 60.0

    def test_overbudget_venue_scores_low(self):
        # budget=0 (20% weight) leaves a max of 80 from the other components.
        # With good capacity/location/features the realistic floor is ~73-74.
        venue = _make_venue(min_price=50000)
        reqs = _make_reqs(max_budget=5000)
        score = score_venue(venue, reqs)
        assert score < 80.0

    def test_score_breakdown_added_to_venue(self):
        venue = _make_venue()
        reqs = _make_reqs()
        score_venue(venue, reqs)
        bd = venue.get("score_breakdown", {})
        assert "capacity_score" in bd
        assert "budget_score" in bd
        assert "location_score" in bd

    def test_relaxed_mode_gives_higher_score_for_tight_fit(self):
        venue = _make_venue(capacity=100)
        reqs = _make_reqs(attendees=150)
        normal = score_venue(dict(_make_venue(capacity=100)), reqs, relaxed=False)
        relaxed = score_venue(dict(_make_venue(capacity=100)), reqs, relaxed=True)
        assert relaxed >= normal


# ── rank_venues ───────────────────────────────────────────────────────────────

class TestRankVenues:
    def test_venues_sorted_descending_by_score(self):
        venues = [
            _make_venue("v1", capacity=50),   # low capacity
            _make_venue("v2", capacity=300),  # high capacity
            _make_venue("v3", capacity=180),  # mid capacity
        ]
        reqs = _make_reqs(attendees=150)
        ranked = rank_venues(venues, reqs)
        scores = [v["match_score"] for v in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_wrong_city_venues_excluded(self):
        venues = [
            _make_venue("v1", city="London"),
            _make_venue("v2", city="Manchester"),
            _make_venue("v3", city="London"),
        ]
        reqs = _make_reqs(city="London")
        ranked = rank_venues(venues, reqs)
        assert all(v["metadata"]["city"] == "London" for v in ranked)
        assert len(ranked) == 2

    def test_duplicate_venue_ids_deduplicated(self):
        venues = [
            _make_venue("v1"),
            _make_venue("v1"),  # same ID, different relevance
        ]
        venues[0]["relevance_score"] = 0.5
        venues[1]["relevance_score"] = 0.9
        reqs = _make_reqs()
        ranked = rank_venues(venues, reqs)
        assert len(ranked) == 1

    def test_empty_input_returns_empty(self):
        assert rank_venues([], _make_reqs()) == []


# ── component-level tests ─────────────────────────────────────────────────────

class TestCapacityComponent:
    def test_exact_fit_scores_full(self):
        reqs = _make_reqs(attendees=100)
        assert _capacity_component({"capacity": "100"}, reqs) == 1.0

    def test_oversized_venue_scores_full(self):
        reqs = _make_reqs(attendees=50)
        assert _capacity_component({"capacity": "200"}, reqs) == 1.0

    def test_no_attendees_returns_default(self):
        reqs = _make_reqs(attendees=0)
        assert _capacity_component({"capacity": "100"}, reqs) == 0.80


class TestBudgetComponent:
    def test_within_budget_scores_full(self):
        reqs = _make_reqs(max_budget=10000)
        assert _budget_component({"min_price": "8000"}, reqs) == 1.0

    def test_way_over_budget_scores_zero(self):
        reqs = _make_reqs(max_budget=5000)
        assert _budget_component({"min_price": "50000"}, reqs) == 0.0

    def test_no_budget_requirement_returns_default(self):
        reqs = _make_reqs(max_budget=0)
        assert _budget_component({"min_price": "10000"}, reqs) == 0.80


class TestLocationComponent:
    def test_city_match_scores_full(self):
        reqs = _make_reqs(city="London")
        assert _location_component({"city": "London"}, reqs) == 1.0

    def test_no_city_requirement_returns_default(self):
        reqs = _make_reqs(city="")
        assert _location_component({"city": "Manchester"}, reqs) == 0.80

    def test_wrong_city_scores_zero(self):
        reqs = _make_reqs(city="London")
        assert _location_component({"city": "Edinburgh"}, reqs) == 0.0
