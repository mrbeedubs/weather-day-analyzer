"""
NOAA Climate Data Online (CDO) API Integration Module

Handles all interactions with NOAA's API including:
- Weather station lookup by coordinates
- Precipitation data retrieval
- Data quality validation
"""

import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from math import radians, cos, sin, asin, sqrt
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Station type priorities (lower = better)
# USW = Weather stations (airports) - best data
# USC = Cooperative stations - good data
# USR = RAWS stations - decent data
# US1 = CoCoRaHS community stations - often incomplete
STATION_TYPE_PRIORITY = {
    "USW": 1,  # Official weather stations (airports, etc.)
    "USC": 2,  # Cooperative observer stations
    "USR": 3,  # RAWS (Remote Automatic Weather Stations)
    "US1": 4,  # CoCoRaHS community stations (often spotty)
}


class NOAAClient:
    """Client for interacting with NOAA Climate Data Online API."""

    BASE_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2"

    def __init__(self, api_token: str, debug: bool = False):
        """
        Initialize NOAA API client.

        Args:
            api_token: NOAA CDO API token (free from https://www.ncdc.noaa.gov/cdo-web/token)
            debug: Enable debug logging
        """
        # Clean the API token to remove any whitespace or invalid characters
        self.api_token = api_token.strip() if api_token else ""
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "token": self.api_token,
            "Content-Type": "application/json"
        })
        self._request_count = 0
        self._last_request_time = None

        if debug:
            logger.setLevel(logging.DEBUG)

    def _rate_limit(self):
        """Implement rate limiting to avoid API throttling."""
        if self._last_request_time:
            elapsed = time.time() - self._last_request_time
            if elapsed < 0.25:  # Max ~4 requests per second
                time.sleep(0.25 - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

    def _make_request(self, endpoint: str, params: Dict = None, max_retries: int = 3) -> Optional[Dict]:
        """
        Make a request to the NOAA API with retry logic.

        Args:
            endpoint: API endpoint (relative to BASE_URL)
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response as dictionary, or None if request fails
        """
        url = f"{self.BASE_URL}/{endpoint}"

        if self.debug:
            logger.debug(f"API Request: {url}")
            logger.debug(f"Parameters: {params}")

        for attempt in range(max_retries):
            self._rate_limit()
            try:
                response = self.session.get(url, params=params, timeout=30)

                if self.debug:
                    logger.debug(f"Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    if self.debug:
                        result_count = len(data.get("results", []))
                        logger.debug(f"Results returned: {result_count}")
                    return data
                elif response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 401:
                    raise ValueError("Invalid NOAA API token. Please check your token.")
                else:
                    logger.warning(f"API returned status {response.status_code}: {response.text[:200]}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return None

            except requests.RequestException as e:
                logger.error(f"Request error: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise ConnectionError(f"Failed to connect to NOAA API: {str(e)}")

        return None

    def _get_station_priority(self, station_id: str) -> int:
        """
        Get priority score for a station based on its type.
        Lower scores are better (more reliable stations).
        """
        # Extract station type prefix (e.g., "USW" from "GHCND:USW00024221")
        if ":" in station_id:
            station_code = station_id.split(":")[1]
        else:
            station_code = station_id

        # Get first 3 characters as type
        station_type = station_code[:3]

        return STATION_TYPE_PRIORITY.get(station_type, 5)

    def _verify_station_has_data(
        self,
        station_id: str,
        start_date: str,
        end_date: str,
        min_records: int = 100
    ) -> Tuple[bool, int]:
        """
        Verify that a station actually has precipitation data for the requested period.

        Note: NOAA API limits requests to 1 year max, so we check one year at a time.

        Args:
            station_id: NOAA station ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            min_records: Minimum number of records required

        Returns:
            Tuple of (has_data, record_count)
        """
        # Parse years from dates
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        total_count = 0

        # Check each year separately (NOAA API has 1-year limit per request)
        for year in range(start_year, end_year + 1):
            params = {
                "datasetid": "GHCND",
                "stationid": station_id,
                "datatypeid": "PRCP",
                "startdate": f"{year}-01-01",
                "enddate": f"{year}-12-31",
                "limit": 1
            }

            result = self._make_request("data", params)

            if result:
                metadata = result.get("metadata", {}).get("resultset", {})
                count = metadata.get("count", 0)
                total_count += count

                # If we find data in any year, that's a good sign
                if count > 0 and self.debug:
                    logger.debug(f"Station {station_id} has {count} records for {year}")

        if self.debug:
            logger.debug(f"Station {station_id} total precipitation records: {total_count}")

        return total_count >= min_records, total_count

    def find_nearest_station(
        self,
        latitude: float,
        longitude: float,
        start_year: int,
        end_year: int,
        search_radius_miles: int = 50,
        verify_data: bool = True
    ) -> Optional[Dict]:
        """
        Find the nearest weather station with precipitation data.

        Args:
            latitude: Latitude of the target location
            longitude: Longitude of the target location
            start_year: Start year for data availability check
            end_year: End year for data availability check
            search_radius_miles: Maximum search radius in miles
            verify_data: Whether to verify station has actual data

        Returns:
            Dictionary with station info, or None if no suitable station found
        """
        # Convert search radius to degrees (approximate)
        radius_degrees = search_radius_miles / 69.0

        # Define bounding box
        min_lat = latitude - radius_degrees
        max_lat = latitude + radius_degrees
        min_lon = longitude - radius_degrees
        max_lon = longitude + radius_degrees

        extent = f"{min_lat},{min_lon},{max_lat},{max_lon}"

        start_date = f"{start_year}-01-01"
        end_date = f"{end_year}-12-31"

        # Search for stations with GHCND (Global Historical Climatology Network Daily) data
        params = {
            "datasetid": "GHCND",
            "datatypeid": "PRCP",  # Precipitation
            "extent": extent,
            "startdate": start_date,
            "enddate": end_date,
            "limit": 1000,
            "sortfield": "datacoverage",
            "sortorder": "desc"
        }

        logger.info(f"Searching for stations near ({latitude}, {longitude})")
        result = self._make_request("stations", params)

        if not result or "results" not in result:
            logger.warning("No stations found in search area")
            return None

        stations = result["results"]
        logger.info(f"Found {len(stations)} potential stations")

        if not stations:
            return None

        # Calculate distances and score all stations
        scored_stations = []

        for station in stations:
            station_lat = station.get("latitude")
            station_lon = station.get("longitude")
            station_id = station.get("id", "")
            data_coverage = station.get("datacoverage", 0)

            if station_lat is None or station_lon is None:
                continue

            # Skip stations with very poor data coverage
            if data_coverage < 0.5:
                continue

            distance = self._haversine_distance(
                latitude, longitude, station_lat, station_lon
            )

            # Get station type priority
            type_priority = self._get_station_priority(station_id)

            # Calculate composite score (lower is better)
            # Weight: 60% station type, 30% distance, 10% coverage
            # Normalize distance to 0-10 scale (50 miles = 10)
            distance_score = min(distance / 5, 10)
            coverage_score = (1 - data_coverage) * 10

            composite_score = (type_priority * 6) + (distance_score * 3) + coverage_score

            scored_stations.append({
                "station": station,
                "distance": distance,
                "type_priority": type_priority,
                "data_coverage": data_coverage,
                "composite_score": composite_score
            })

        # Sort by composite score (lower is better)
        scored_stations.sort(key=lambda x: x["composite_score"])

        if self.debug:
            logger.debug("Top 5 candidate stations:")
            for i, s in enumerate(scored_stations[:5]):
                logger.debug(
                    f"  {i+1}. {s['station']['id']} - {s['station']['name'][:40]} - "
                    f"dist: {s['distance']:.1f}mi, type: {s['type_priority']}, "
                    f"coverage: {s['data_coverage']:.0%}, score: {s['composite_score']:.1f}"
                )

        # Try stations in order until we find one with actual data
        years_needed = end_year - start_year + 1
        min_records = years_needed * 200  # Expect ~365 records per year, require 200

        for scored in scored_stations[:10]:  # Try top 10 candidates
            station = scored["station"]
            station_id = station["id"]
            distance = scored["distance"]

            logger.info(f"Checking station: {station['name']} ({station_id})")

            if verify_data:
                has_data, record_count = self._verify_station_has_data(
                    station_id, start_date, end_date, min_records
                )

                if not has_data:
                    logger.info(f"  Station has insufficient data ({record_count} records), trying next...")
                    continue

                logger.info(f"  Station has {record_count} precipitation records - SELECTED")

            station["distance_miles"] = round(distance, 1)
            station["direction"] = self._get_direction(
                latitude, longitude, station["latitude"], station["longitude"]
            )

            return station

        # If no verified station found, return best candidate with warning
        if scored_stations:
            logger.warning("No stations with verified data found, returning best candidate")
            best = scored_stations[0]
            station = best["station"]
            station["distance_miles"] = round(best["distance"], 1)
            station["direction"] = self._get_direction(
                latitude, longitude, station["latitude"], station["longitude"]
            )
            station["data_warning"] = "Could not verify precipitation data availability"
            return station

        return None

    def get_precipitation_data(
        self,
        station_id: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        Get daily precipitation data for a station.

        Note: NOAA API limits requests to 1 year max, so we fetch year by year.

        Args:
            station_id: NOAA station ID (e.g., "GHCND:USW00023174")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of precipitation records
        """
        all_data = []

        # Parse years from dates
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        logger.info(f"Fetching precipitation data for {station_id} from {start_date} to {end_date}")
        logger.info(f"Will fetch {end_year - start_year + 1} years of data (NOAA API requires year-by-year requests)")

        # Fetch each year separately (NOAA API has 1-year limit per request)
        for year in range(start_year, end_year + 1):
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"

            logger.info(f"Fetching year {year}...")

            offset = 1
            limit = 1000
            year_records = 0

            while True:
                params = {
                    "datasetid": "GHCND",
                    "stationid": station_id,
                    "datatypeid": "PRCP",
                    "startdate": year_start,
                    "enddate": year_end,
                    "units": "standard",  # Returns precipitation in tenths of inches
                    "limit": limit,
                    "offset": offset
                }

                result = self._make_request("data", params)

                if not result:
                    if self.debug:
                        logger.debug(f"No data returned for {year} at offset {offset}")
                    break

                if "results" not in result:
                    if self.debug:
                        logger.debug(f"No 'results' key in response for {year} at offset {offset}")
                    break

                records = result["results"]
                all_data.extend(records)
                year_records += len(records)

                if self.debug:
                    logger.debug(f"Fetched {len(records)} records for {year} at offset {offset}")

                # Check if there are more results for this year
                metadata = result.get("metadata", {}).get("resultset", {})
                total_count = metadata.get("count", 0)

                if offset + limit > total_count:
                    break

                offset += limit

            logger.info(f"  Year {year}: {year_records} records")

        logger.info(f"Total precipitation records retrieved: {len(all_data)}")

        if self.debug and all_data:
            # Show sample of data
            sample = all_data[0]
            logger.debug(f"Sample record: {sample}")

        return all_data

    def find_stations_with_data(
        self,
        latitude: float,
        longitude: float,
        start_year: int,
        end_year: int,
        max_stations: int = 5,
        search_radius_miles: int = 50
    ) -> List[Dict]:
        """
        Find multiple stations with verified precipitation data.
        Useful for showing alternatives to the user.

        Args:
            latitude: Latitude of the target location
            longitude: Longitude of the target location
            start_year: Start year
            end_year: End year
            max_stations: Maximum number of stations to return
            search_radius_miles: Search radius in miles

        Returns:
            List of station dictionaries with data verification info
        """
        radius_degrees = search_radius_miles / 69.0

        min_lat = latitude - radius_degrees
        max_lat = latitude + radius_degrees
        min_lon = longitude - radius_degrees
        max_lon = longitude + radius_degrees

        extent = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        start_date = f"{start_year}-01-01"
        end_date = f"{end_year}-12-31"

        params = {
            "datasetid": "GHCND",
            "datatypeid": "PRCP",
            "extent": extent,
            "startdate": start_date,
            "enddate": end_date,
            "limit": 100,
            "sortfield": "datacoverage",
            "sortorder": "desc"
        }

        result = self._make_request("stations", params)

        if not result or "results" not in result:
            return []

        stations = result["results"]
        verified_stations = []

        years_needed = end_year - start_year + 1
        min_records = years_needed * 200

        for station in stations:
            if len(verified_stations) >= max_stations:
                break

            station_id = station["id"]
            has_data, record_count = self._verify_station_has_data(
                station_id, start_date, end_date, min_records
            )

            if has_data:
                distance = self._haversine_distance(
                    latitude, longitude,
                    station["latitude"], station["longitude"]
                )

                verified_stations.append({
                    "id": station_id,
                    "name": station["name"],
                    "distance_miles": round(distance, 1),
                    "record_count": record_count,
                    "data_coverage": station.get("datacoverage", 0)
                })

        return verified_stations

    def get_available_years(self, station_id: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Get the range of years with available data for a station.

        Args:
            station_id: NOAA station ID

        Returns:
            Tuple of (start_year, end_year) or (None, None) if unavailable
        """
        params = {
            "datasetid": "GHCND",
            "stationid": station_id
        }

        result = self._make_request("stations", params)

        if result and "results" in result and result["results"]:
            station = result["results"][0]
            min_date = station.get("mindate", "")
            max_date = station.get("maxdate", "")

            try:
                start_year = int(min_date[:4]) if min_date else None
                end_year = int(max_date[:4]) if max_date else None
                return start_year, end_year
            except (ValueError, IndexError):
                pass

        return None, None

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points in miles.
        """
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))

        # Earth's radius in miles
        r = 3956

        return c * r

    @staticmethod
    def _get_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
        """
        Get cardinal direction from point 1 to point 2.
        """
        lat_diff = lat2 - lat1
        lon_diff = lon2 - lon1

        ns = "N" if lat_diff > 0 else "S" if lat_diff < 0 else ""
        ew = "E" if lon_diff > 0 else "W" if lon_diff < 0 else ""

        if abs(lat_diff) < 0.01:
            return ew or "at location"
        if abs(lon_diff) < 0.01:
            return ns or "at location"

        return f"{ns}{ew}"

    def validate_token(self) -> bool:
        """
        Validate the API token by making a test request.

        Returns:
            True if token is valid, False otherwise
        """
        try:
            params = {"limit": 1}
            result = self._make_request("datasets", params)
            return result is not None
        except ValueError:
            return False
        except ConnectionError:
            raise
