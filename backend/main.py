import random
import time
from threading import Lock
import os

import requests
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

OVERPASS_API_ENDPOINT = "https://overpass-api.de/api/interpreter"
OVERPASS_API_QUERY = """
[out:json];
area["name"="Seattle"]->.searchArea;
node["amenity"="cafe"](area.searchArea);
out;
"""

CACHE_FRESH_TTL_SECONDS = int(os.getenv("CAFE_CACHE_FRESH_TTL_SECONDS", "21600"))
CACHE_MAX_STALE_SECONDS = int(os.getenv("CAFE_CACHE_MAX_STALE_SECONDS", "604800"))
OVERPASS_TIMEOUT_SECONDS = int(os.getenv("OVERPASS_TIMEOUT_SECONDS", "30"))
OVERPASS_MAX_RETRIES = int(os.getenv("OVERPASS_MAX_RETRIES", "3"))
OVERPASS_RETRY_BACKOFF_SECONDS = float(
    os.getenv("OVERPASS_RETRY_BACKOFF_SECONDS", "1.0")
)

cache_lock = Lock()
cafe_cache = {"cafes": [], "updated_at": 0.0}


def format_address(tags: dict) -> str:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    if not any(parts):
        return "Not available. Please check online."

    house_number = tags.get("addr:housenumber")
    street = tags.get("addr:street")
    city = tags.get("addr:city")
    postcode = tags.get("addr:postcode")

    street_line = " ".join(part for part in [house_number, street] if part)
    city_line_parts = []
    if city:
        city_line_parts.append(city)
        city_line_parts.append("WA")
    if postcode:
        city_line_parts.append(postcode)
    city_line = " ".join(city_line_parts)

    if street_line and city_line:
        return f"{street_line}, {city_line}"
    return street_line or city_line


def fetch_cafes_from_overpass() -> list[dict]:
    last_exc = None

    for attempt in range(1, OVERPASS_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url=OVERPASS_API_ENDPOINT,
                data=OVERPASS_API_QUERY,
                timeout=OVERPASS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == OVERPASS_MAX_RETRIES:
                raise
            time.sleep(OVERPASS_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    else:
        if last_exc is not None:
            raise last_exc
        raise requests.RequestException("Unknown Overpass fetch error")

    cafes = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name") or "Unknown cafe"
        cafes.append({"name": name, "address": format_address(tags)})

    return cafes


def cafe_response(
    cafe: dict, cache_status: str, cache_age_seconds: float
) -> JSONResponse:
    headers = {
        "X-Cache": cache_status,
        "X-Cache-Age-Seconds": str(max(0, int(cache_age_seconds))),
    }
    return JSONResponse(content=cafe, headers=headers)


@app.get("/cafes", status_code=status.HTTP_200_OK)
def get_cafes() -> dict:
    now = time.time()

    with cache_lock:
        cached_cafes = cafe_cache["cafes"]
        updated_at = cafe_cache["updated_at"]

    cache_age_seconds = now - updated_at if cached_cafes else float("inf")

    if cached_cafes and cache_age_seconds <= CACHE_FRESH_TTL_SECONDS:
        return cafe_response(
            cafe=random.choice(cached_cafes),
            cache_status="fresh",
            cache_age_seconds=cache_age_seconds,
        )

    try:
        fresh_cafes = fetch_cafes_from_overpass()
    except requests.RequestException as exc:
        if cached_cafes and cache_age_seconds <= CACHE_MAX_STALE_SECONDS:
            return cafe_response(
                cafe=random.choice(cached_cafes),
                cache_status="stale",
                cache_age_seconds=cache_age_seconds,
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch cafe data from Overpass API.",
        ) from exc

    if fresh_cafes:
        fresh_now = time.time()
        with cache_lock:
            cafe_cache["cafes"] = fresh_cafes
            cafe_cache["updated_at"] = fresh_now
        return cafe_response(
            cafe=random.choice(fresh_cafes),
            cache_status="miss",
            cache_age_seconds=0,
        )

    if cached_cafes and cache_age_seconds <= CACHE_MAX_STALE_SECONDS:
        return cafe_response(
            cafe=random.choice(cached_cafes),
            cache_status="stale",
            cache_age_seconds=cache_age_seconds,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No cafes found for Seattle.",
    )
