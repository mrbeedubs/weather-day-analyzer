"""
Geocoding Module

Handles conversion of US zip codes to latitude/longitude coordinates.
Uses multiple fallback methods for reliability.
"""

import requests
from typing import Optional, Tuple, Dict
import re
import os
import time
import threading

_GEOCODE_LOCK = threading.Lock()
_GEOCODE_CACHE = {}
_LAST_NOMINATIM = 0.0


class ZipCodeGeocoder:
    """Convert US zip codes to geographic coordinates."""

    # US Census Geocoder API (free, no key required)
    CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

    # Nominatim (OpenStreetMap) - backup
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self):
        self.NOMINATIM_URL = os.environ.get("NOMINATIM_URL", self.NOMINATIM_URL)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "WeatherDayAnalyzer/1.0 (Construction Weather Analysis Tool)"
        })

    def validate_zip_code(self, zip_code: str) -> bool:
        """
        Validate US zip code format.

        Args:
            zip_code: Zip code to validate

        Returns:
            True if valid format, False otherwise
        """
        # Match 5 digit or 5+4 format
        pattern = r"^\d{5}(-\d{4})?$"
        return bool(re.match(pattern, zip_code.strip()))

    def geocode(self, zip_code: str) -> Optional[Dict]:
        """
        Convert zip code to coordinates and location info.

        Args:
            zip_code: US zip code (5 or 9 digit format)

        Returns:
            Dictionary with latitude, longitude, and location name
            or None if geocoding fails
        """
        if not self.validate_zip_code(zip_code):
            return None

        # Use only first 5 digits
        zip_code = zip_code.strip()[:5]

        with _GEOCODE_LOCK:
            return self._geocode_cached(zip_code)

    def _geocode_cached(self, zip_code):
        if zip_code in _GEOCODE_CACHE:
            return dict(_GEOCODE_CACHE[zip_code])
        # Try Census Geocoder first
        result = self._geocode_census(zip_code)
        if result:
            _GEOCODE_CACHE[zip_code] = result
            return dict(result)

        # Fallback to Nominatim
        result = self._geocode_nominatim(zip_code)
        if result:
            _GEOCODE_CACHE[zip_code] = result
            return dict(result)

        return None

    def _geocode_census(self, zip_code: str) -> Optional[Dict]:
        """
        Geocode using US Census Bureau API.
        """
        params = {
            "address": zip_code,
            "benchmark": "Public_AR_Current",
            "format": "json"
        }

        try:
            response = self.session.get(self.CENSUS_URL, params=params, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()
            matches = data.get("result", {}).get("addressMatches", [])

            if not matches:
                return None

            match = matches[0]
            coords = match.get("coordinates", {})
            address = match.get("matchedAddress", "")

            # Parse city/state from matched address
            city, state = self._parse_location(address)

            return {
                "latitude": coords.get("y"),
                "longitude": coords.get("x"),
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "full_location": f"{city}, {state} {zip_code}" if city and state else zip_code
            }

        except (requests.RequestException, KeyError, ValueError):
            return None

    def _geocode_nominatim(self, zip_code: str) -> Optional[Dict]:
        """
        Geocode using OpenStreetMap Nominatim as fallback.
        """
        params = {
            "q": f"{zip_code}, USA",
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": "us"
        }

        try:
            global _LAST_NOMINATIM
            delay = 1.05 - (time.monotonic() - _LAST_NOMINATIM)
            if delay > 0:
                time.sleep(delay)
            _LAST_NOMINATIM = time.monotonic()
            response = self.session.get(self.NOMINATIM_URL, params=params, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()

            if not data:
                return None

            result = data[0]
            address = result.get("address", {})

            city = address.get("city") or address.get("town") or address.get("village") or ""
            state = address.get("state", "")

            return {
                "latitude": float(result.get("lat")),
                "longitude": float(result.get("lon")),
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "full_location": f"{city}, {state} {zip_code}" if city and state else zip_code
            }

        except (requests.RequestException, KeyError, ValueError, IndexError):
            return None

    @staticmethod
    def _parse_location(address: str) -> Tuple[str, str]:
        """
        Parse city and state from a matched address string.

        Args:
            address: Address string like "CITY, STATE, ZIP"

        Returns:
            Tuple of (city, state)
        """
        try:
            parts = address.split(",")
            if len(parts) >= 2:
                city = parts[0].strip().title()
                state = parts[1].strip()
                return city, state
        except (IndexError, AttributeError):
            pass

        return "", ""


def get_coordinates(zip_code: str) -> Optional[Dict]:
    """
    Convenience function to geocode a zip code.

    Args:
        zip_code: US zip code

    Returns:
        Dictionary with coordinates and location info, or None
    """
    geocoder = ZipCodeGeocoder()
    return geocoder.geocode(zip_code)
