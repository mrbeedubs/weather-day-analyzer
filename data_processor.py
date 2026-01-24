"""
Data Processing Module

Processes raw precipitation data from NOAA to calculate:
- Days with >= 0.5" precipitation per month
- Monthly averages across multiple years
- Data quality metrics and gap detection
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# Default precipitation threshold in inches (0.5")
DEFAULT_THRESHOLD = 0.5

# NOAA API with units=standard returns precipitation DIRECTLY in inches
# Example: value of 0.27 = 0.27 inches (NOT tenths - already converted)
# No division needed when using units=standard
NOAA_PRCP_DIVISOR = 1.0  # Values already in inches with units=standard

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


class PrecipitationProcessor:
    """Process precipitation data to identify significant rain days."""

    def __init__(self, precipitation_data: List[Dict], start_year: int, end_year: int, threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize processor with raw NOAA precipitation data.

        Args:
            precipitation_data: List of NOAA precipitation records
            start_year: Start year of analysis period
            end_year: End year of analysis period
            threshold: Precipitation threshold in inches (default 0.5")
        """
        self.raw_data = precipitation_data
        self.start_year = start_year
        self.end_year = end_year
        self.threshold = threshold
        self.years = list(range(start_year, end_year + 1))

        # Processed data storage
        self.daily_precip: Dict[str, float] = {}  # date -> inches
        self.monthly_rain_days: Dict[int, Dict[int, int]] = {}  # year -> month -> count
        self.data_quality: Dict[int, Dict[int, str]] = {}  # year -> month -> quality
        self.missing_years: List[int] = []
        self.partial_years: List[int] = []

        self._process_data()

    def _process_data(self):
        """Process raw precipitation data into structured format."""
        # Parse raw data into daily precipitation values
        rain_day_count = 0
        max_precip = 0.0

        for record in self.raw_data:
            date_str = record.get("date", "")[:10]  # YYYY-MM-DD
            value = record.get("value", 0)

            # With units=standard, values are already in inches
            precip_inches = value / NOAA_PRCP_DIVISOR

            self.daily_precip[date_str] = precip_inches

            if precip_inches >= self.threshold:
                rain_day_count += 1
            if precip_inches > max_precip:
                max_precip = precip_inches

        logger.info(f"Processed {len(self.raw_data)} records (threshold: {self.threshold}\")")
        logger.info(f"Max precipitation value: {max_precip:.2f} inches")
        logger.info(f"Days with >= {self.threshold}\" rain: {rain_day_count}")

        # Initialize monthly rain day counts for all years/months
        for year in self.years:
            self.monthly_rain_days[year] = {m: 0 for m in range(1, 13)}
            self.data_quality[year] = {m: "complete" for m in range(1, 13)}

        # Count rain days per month using configured threshold
        for date_str, precip in self.daily_precip.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                year = date.year
                month = date.month

                if year in self.monthly_rain_days:
                    if precip >= self.threshold:
                        self.monthly_rain_days[year][month] += 1

            except ValueError:
                continue

        # Log monthly totals for verification
        for year in self.years:
            year_total = sum(self.monthly_rain_days[year].values())
            logger.info(f"Year {year} total rain days: {year_total}")

        # Analyze data quality
        self._analyze_data_quality()

    def _analyze_data_quality(self):
        """Analyze data completeness and identify gaps."""
        days_in_month = {
            1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
            7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
        }

        for year in self.years:
            year_data_count = 0
            year_expected_count = 365 + (1 if self._is_leap_year(year) else 0)

            for month in range(1, 13):
                expected_days = days_in_month[month]
                if month == 2 and self._is_leap_year(year):
                    expected_days = 29

                # Count actual data points for this month
                actual_days = sum(
                    1 for date_str in self.daily_precip
                    if date_str.startswith(f"{year}-{month:02d}")
                )

                year_data_count += actual_days

                # Determine data quality for this month
                if actual_days == 0:
                    self.data_quality[year][month] = "missing"
                elif actual_days < expected_days * 0.5:
                    self.data_quality[year][month] = "sparse"
                elif actual_days < expected_days * 0.9:
                    self.data_quality[year][month] = "partial"
                else:
                    self.data_quality[year][month] = "complete"

            # Determine overall year quality
            if year_data_count == 0:
                self.missing_years.append(year)
            elif year_data_count < year_expected_count * 0.8:
                self.partial_years.append(year)

    @staticmethod
    def _is_leap_year(year: int) -> bool:
        """Check if a year is a leap year."""
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def get_monthly_rain_days(self) -> Dict[int, Dict[int, Optional[int]]]:
        """
        Get rain day counts per month for each year.

        Returns:
            Dictionary: year -> month -> count (None if data missing)
        """
        result = {}

        for year in self.years:
            result[year] = {}
            for month in range(1, 13):
                quality = self.data_quality[year][month]
                if quality == "missing":
                    result[year][month] = None
                else:
                    result[year][month] = self.monthly_rain_days[year][month]

        return result

    def get_monthly_averages(self) -> Dict[int, Tuple[Optional[float], bool]]:
        """
        Calculate average rain days per month across all years.

        Returns:
            Dictionary: month -> (average, is_approximate)
            is_approximate is True if some years are missing data
        """
        averages = {}

        for month in range(1, 13):
            values = []
            missing_count = 0

            for year in self.years:
                quality = self.data_quality[year][month]
                if quality == "missing":
                    missing_count += 1
                else:
                    values.append(self.monthly_rain_days[year][month])

            if not values:
                averages[month] = (None, False)
            else:
                avg = sum(values) / len(values)
                is_approximate = missing_count > 0
                averages[month] = (round(avg, 1), is_approximate)

        return averages

    def get_yearly_totals(self) -> Dict[int, Optional[int]]:
        """
        Get total rain days per year.

        Returns:
            Dictionary: year -> total count (None if insufficient data)
        """
        totals = {}

        for year in self.years:
            if year in self.missing_years:
                totals[year] = None
            else:
                # Sum all months, treating missing months as 0
                total = sum(
                    self.monthly_rain_days[year][m]
                    for m in range(1, 13)
                    if self.data_quality[year][m] != "missing"
                )

                # Check if we have enough data to report
                missing_months = sum(
                    1 for m in range(1, 13)
                    if self.data_quality[year][m] == "missing"
                )

                if missing_months > 3:  # More than 3 months missing
                    totals[year] = None
                else:
                    totals[year] = total

        return totals

    def get_average_total(self) -> Tuple[Optional[float], bool]:
        """
        Get average total rain days per year.

        Returns:
            Tuple: (average, is_approximate)
        """
        totals = self.get_yearly_totals()
        valid_totals = [v for v in totals.values() if v is not None]

        if not valid_totals:
            return (None, False)

        avg = sum(valid_totals) / len(valid_totals)
        is_approximate = len(valid_totals) < len(self.years)

        return (round(avg, 1), is_approximate)

    def get_data_quality_summary(self) -> Dict:
        """
        Get summary of data quality issues.

        Returns:
            Dictionary with quality metrics
        """
        return {
            "missing_years": sorted(self.missing_years),
            "partial_years": sorted(self.partial_years),
            "total_years_requested": len(self.years),
            "complete_years": len(self.years) - len(self.missing_years) - len(self.partial_years),
            "data_coverage_percent": round(
                (1 - len(self.missing_years) / len(self.years)) * 100, 1
            ) if self.years else 0
        }

    def get_analysis_summary(self) -> Dict:
        """
        Get complete analysis summary for report generation.

        Returns:
            Dictionary with all processed data
        """
        return {
            "years": self.years,
            "monthly_rain_days": self.get_monthly_rain_days(),
            "monthly_averages": self.get_monthly_averages(),
            "yearly_totals": self.get_yearly_totals(),
            "average_total": self.get_average_total(),
            "data_quality": self.get_data_quality_summary(),
            "month_names": MONTH_NAMES,
            "threshold_inches": self.threshold
        }


def process_precipitation_data(
    raw_data: List[Dict],
    start_year: int,
    end_year: int
) -> Dict:
    """
    Convenience function to process precipitation data.

    Args:
        raw_data: Raw NOAA precipitation records
        start_year: Start year of analysis
        end_year: End year of analysis

    Returns:
        Complete analysis summary
    """
    processor = PrecipitationProcessor(raw_data, start_year, end_year)
    return processor.get_analysis_summary()
