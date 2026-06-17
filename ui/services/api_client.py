import requests


def get_health(base_url: str = "http://api:8000") -> dict:
    response = requests.get(f"{base_url}/api/health", timeout=5)
    response.raise_for_status()
    return response.json()
