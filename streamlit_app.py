"""
NOAA Weather Day Analysis - Streamlit Application

A professional tool for analyzing historical rainfall data to support
construction contract weather day allowances.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import io

from noaa_api import NOAAClient
from geocoder import get_coordinates, ZipCodeGeocoder
from data_processor import PrecipitationProcessor, MONTH_NAMES
from report_generator import ReportGenerator

# Page configuration
st.set_page_config(
    page_title="Weather Day Analyzer",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional appearance
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #4a5568;
        margin-bottom: 2rem;
    }
    .station-info {
        background-color: #e8f4fc;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2c5282;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f7fafc;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }
    .data-note {
        background-color: #fef3c7;
        padding: 0.75rem;
        border-radius: 6px;
        border-left: 4px solid #f59e0b;
        font-size: 0.9rem;
    }
    .stDataFrame {
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# Time period configurations
TIME_PERIODS = {
    "1yr": {"years": 1, "name": "1-Year", "min_data_years": 1},
    "2yr": {"years": 2, "name": "2-Year", "min_data_years": 2},
    "5yr": {"years": 5, "name": "5-Year", "min_data_years": 3},
    "10yr": {"years": 10, "name": "10-Year", "min_data_years": 6},
}

# Threshold options with display labels
THRESHOLD_OPTIONS = {
    0.10: '1/10" (0.10")',
    0.25: '1/4" (0.25")',
    0.50: '1/2" (0.50")',
    0.75: '3/4" (0.75")',
    1.00: '1" (1.00")',
}


def clean_api_key(key: str) -> str:
    """Clean and validate API key, removing any whitespace or invalid characters."""
    if not key:
        return ""
    cleaned = key.strip().strip('"').strip("'").strip()
    cleaned = cleaned.replace('\n', '').replace('\r', '').replace('\t', '')
    return cleaned


def get_api_key():
    """Get NOAA API key from secrets."""
    try:
        raw_key = st.secrets["NOAA_API_KEY"]
        return clean_api_key(raw_key)
    except (KeyError, FileNotFoundError):
        return None


def get_analysis_years(period: str) -> tuple:
    """Get start and end years for analysis period."""
    current_year = datetime.now().year
    years_back = TIME_PERIODS.get(period, TIME_PERIODS["5yr"])["years"]
    end_year = current_year - 1
    start_year = end_year - years_back + 1
    return start_year, end_year


def format_threshold(threshold: float) -> str:
    """Format threshold for display."""
    if threshold >= 1.0:
        return f'{threshold:.2f}"'
    elif threshold == 0.5:
        return '1/2"'
    elif threshold == 0.25:
        return '1/4"'
    elif threshold == 0.75:
        return '3/4"'
    elif threshold == 0.1:
        return '1/10"'
    else:
        return f'{threshold:.2f}"'


@st.cache_data(ttl=3600, show_spinner=False)
def find_station_cached(lat, lon, start_year, end_year, api_key):
    """Cache station lookup to reduce API calls."""
    client = NOAAClient(api_key)
    return client.find_nearest_station(lat, lon, start_year, end_year)


@st.cache_data(ttl=3600, show_spinner=False)
def get_precipitation_cached(station_id, start_date, end_date, api_key):
    """Cache precipitation data to reduce API calls."""
    client = NOAAClient(api_key)
    return client.get_precipitation_data(station_id, start_date, end_date)


def process_with_threshold(precip_data, start_year, end_year, threshold):
    """Process precipitation data with custom threshold."""
    processor = PrecipitationProcessor(precip_data, start_year, end_year, threshold)
    return processor.get_analysis_summary()


def create_results_dataframe(analysis_data):
    """Convert analysis data to a formatted DataFrame."""
    years = analysis_data["years"]
    monthly_data = analysis_data["monthly_rain_days"]
    averages = analysis_data["monthly_averages"]

    data = []
    for month_idx, month_name in enumerate(MONTH_NAMES, 1):
        row = {"Month": month_name}
        for year in years:
            value = monthly_data.get(year, {}).get(month_idx)
            # Convert all values to strings to avoid Arrow serialization issues
            row[str(year)] = str(value) if value is not None else "-"

        avg_value, is_approx = averages.get(month_idx, (None, False))
        if avg_value is not None:
            row["Average"] = f"~{avg_value}" if is_approx else str(avg_value)
        else:
            row["Average"] = "-"

        data.append(row)

    yearly_totals = analysis_data["yearly_totals"]
    avg_total = analysis_data["average_total"]

    total_row = {"Month": "TOTAL"}
    for year in years:
        value = yearly_totals.get(year)
        # Convert all values to strings to avoid Arrow serialization issues
        total_row[str(year)] = str(value) if value is not None else "-"

    avg_val, is_approx = avg_total
    if avg_val is not None:
        total_row["Average"] = f"~{avg_val}" if is_approx else str(avg_val)
    else:
        total_row["Average"] = "-"

    data.append(total_row)

    return pd.DataFrame(data)


def main():
    # Header
    st.markdown('<p class="main-header">Weather Day Analyzer</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Historical precipitation analysis for construction weather day allowances</p>', unsafe_allow_html=True)

    # Get API key from secrets
    api_key = get_api_key()

    # Check if API key is configured
    if not api_key:
        st.error("⚠️ NOAA API key not configured")
        st.markdown("""
        ### Setup Required

        To use this application, you need to configure your NOAA API key:

        **For Local Development:**
        1. Create file `.streamlit/secrets.toml`
        2. Add: `NOAA_API_KEY="your-key-here"`

        **For Streamlit Cloud:**
        1. Go to your app settings
        2. Click "Secrets"
        3. Add: `NOAA_API_KEY="your-key-here"`

        **Get a Free API Key:**
        1. Visit [NOAA CDO Token Request](https://www.ncdc.noaa.gov/cdo-web/token)
        2. Enter your email
        3. Check your inbox for the token
        """)
        return

    # Sidebar for inputs
    with st.sidebar:
        st.header("Configuration")
        st.success("✅ API Key Configured")

        st.divider()

        # Zip code input
        zip_code = st.text_input(
            "US Zip Code",
            placeholder="e.g., 97401",
            max_chars=10,
            help="Enter a 5-digit US zip code"
        )

        st.divider()

        # Threshold selector
        st.subheader("Rain Threshold")
        threshold = st.selectbox(
            "Precipitation per day",
            options=list(THRESHOLD_OPTIONS.keys()),
            format_func=lambda x: THRESHOLD_OPTIONS[x],
            index=2,  # Default to 0.5"
            help="Count days with at least this much precipitation"
        )
        st.caption(f"Count days with ≥{format_threshold(threshold)} of rain")

        st.divider()

        # Period selection
        st.subheader("Analysis Periods")
        selected_periods = []

        col1, col2 = st.columns(2)
        with col1:
            if st.checkbox("1 Year"):
                selected_periods.append("1yr")
            if st.checkbox("5 Years", value=True):
                selected_periods.append("5yr")
        with col2:
            if st.checkbox("2 Years"):
                selected_periods.append("2yr")
            if st.checkbox("10 Years"):
                selected_periods.append("10yr")

        st.divider()

        # Analyze button
        analyze_clicked = st.button(
            "Analyze Precipitation Data",
            type="primary",
            width="stretch",
            disabled=not (zip_code and selected_periods)
        )

    # Main content area
    if analyze_clicked and zip_code and selected_periods:
        # Validate zip code
        geocoder = ZipCodeGeocoder()
        if not geocoder.validate_zip_code(zip_code):
            st.error("Invalid zip code format. Please enter a 5-digit US zip code.")
            return

        progress_bar = st.progress(0, text="Finding location coordinates...")

        try:
            # Step 1: Geocode
            location = get_coordinates(zip_code)
            if not location:
                st.error(f"Could not find coordinates for zip code {zip_code}")
                return

            progress_bar.progress(20, text="Searching for weather stations...")

            # Step 2: Find station
            max_years = max(TIME_PERIODS[p]["years"] for p in selected_periods)
            current_year = datetime.now().year
            end_year = current_year - 1
            start_year = end_year - max_years + 1

            station = find_station_cached(
                location["latitude"],
                location["longitude"],
                start_year,
                end_year,
                api_key
            )

            if not station:
                st.error(f"No weather stations with precipitation data found near {zip_code}. Try a nearby zip code.")
                return

            progress_bar.progress(40, text="Retrieving precipitation data...")

            # Display station info
            st.markdown(f"""
            <div class="station-info">
                <strong>Weather Station:</strong> {station['name']}<br>
                <strong>Location:</strong> {station.get('distance_miles', '?')} miles {station.get('direction', '')} of {location['full_location']}<br>
                <strong>Station ID:</strong> {station['id']}
            </div>
            """, unsafe_allow_html=True)

            if station.get("data_warning"):
                st.markdown(f'<div class="data-note">⚠️ {station["data_warning"]}</div>', unsafe_allow_html=True)

            # Step 3: Process each period
            results = {}
            progress_increment = 50 / len(selected_periods)

            for i, period in enumerate(sorted(selected_periods, key=lambda x: TIME_PERIODS[x]["years"])):
                period_start, period_end = get_analysis_years(period)
                period_config = TIME_PERIODS[period]

                progress_bar.progress(
                    int(40 + (i * progress_increment)),
                    text=f"Fetching {period_config['name']} data..."
                )

                # Get precipitation data
                precip_data = get_precipitation_cached(
                    station["id"],
                    f"{period_start}-01-01",
                    f"{period_end}-12-31",
                    api_key
                )

                # Process data with selected threshold
                analysis = process_with_threshold(precip_data, period_start, period_end, threshold)

                results[period] = {
                    "period_name": period_config["name"],
                    "start_year": period_start,
                    "end_year": period_end,
                    "analysis": analysis,
                    "threshold": threshold
                }

            progress_bar.progress(100, text="Analysis complete!")

            # Display results in tabs
            if results:
                st.subheader(f"Historical Rain Days with ≥{format_threshold(threshold)} Precipitation")

                tabs = st.tabs([results[p]["period_name"] for p in sorted(results.keys(), key=lambda x: TIME_PERIODS[x]["years"])])

                for tab, period in zip(tabs, sorted(results.keys(), key=lambda x: TIME_PERIODS[x]["years"])):
                    with tab:
                        result = results[period]
                        analysis = result["analysis"]

                        quality = analysis["data_quality"]
                        if quality["missing_years"]:
                            st.warning(f"Missing data for years: {', '.join(map(str, quality['missing_years']))}")

                        df = create_results_dataframe(analysis)

                        st.dataframe(
                            df,
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "Month": st.column_config.TextColumn("Month", width="medium"),
                                "Average": st.column_config.TextColumn(f"{result['period_name']} Avg", width="small")
                            }
                        )

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            avg_total, _ = analysis["average_total"]
                            st.metric("Avg Rain Days/Year", f"{avg_total or '-'}")
                        with col2:
                            st.metric("Years Analyzed", len(analysis["years"]))
                        with col3:
                            st.metric("Data Coverage", f"{quality['data_coverage_percent']}%")

                        st.divider()

                        # Export options
                        st.subheader("Export Report")
                        export_col1, export_col2, export_col3 = st.columns(3)

                        # Update analysis with threshold for report
                        analysis["threshold_inches"] = threshold

                        generator = ReportGenerator(station, location, analysis, result["period_name"])

                        # Format threshold for filename (e.g., 0.50 -> "0.50in")
                        threshold_str = f"{threshold:.2f}in"

                        with export_col1:
                            try:
                                excel_data = generator.generate_excel()
                                st.download_button(
                                    "📊 Download Excel",
                                    data=excel_data,
                                    file_name=f"weather_{zip_code}_{threshold_str}_{period}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    width="stretch"
                                )
                            except Exception as e:
                                st.error(f"Excel export unavailable: {e}")

                        with export_col2:
                            csv_data = generator.generate_csv()
                            st.download_button(
                                "📄 Download CSV",
                                data=csv_data,
                                file_name=f"weather_{zip_code}_{threshold_str}_{period}.csv",
                                mime="text/csv",
                                width="stretch"
                            )

                        with export_col3:
                            try:
                                pdf_data = generator.generate_pdf()
                                st.download_button(
                                    "📑 Download PDF",
                                    data=pdf_data,
                                    file_name=f"weather_{zip_code}_{threshold_str}_{period}.pdf",
                                    mime="application/pdf",
                                    width="stretch"
                                )
                            except Exception as e:
                                st.error(f"PDF export unavailable: {e}")

        except ValueError as e:
            st.error(f"API Error: {str(e)}")
        except ConnectionError as e:
            st.error(f"Connection Error: {str(e)}")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            if st.checkbox("Show error details"):
                st.exception(e)

    else:
        # Show instructions when no analysis is running
        st.info("👈 Enter a zip code, select a rain threshold and analysis periods, then click **Analyze Precipitation Data**")

        with st.expander("About This Tool"):
            st.markdown("""
            ### Weather Day Analyzer

            This tool analyzes historical rainfall data from NOAA weather stations to support
            construction contract weather day allowances.

            **Features:**
            - Find the nearest NOAA weather station to any US zip code
            - Analyze 1, 2, 5, or 10 years of historical data
            - **Configurable rain threshold** (1/10", 1/4", 1/2", 3/4", 1")
            - Export professional reports in Excel, CSV, or PDF format

            **Data Source:**
            - NOAA Climate Data Online (CDO)
            - Global Historical Climatology Network Daily (GHCND)

            **For Construction Professionals:**
            - Document historical weather patterns for bid preparation
            - Support weather delay claims with official NOAA data
            - Establish baseline weather expectations for contracts
            """)

        with st.expander("Sample Zip Codes to Try"):
            st.markdown("""
            | Zip Code | Location | Climate |
            |----------|----------|---------|
            | 97401 | Eugene, OR | Wet (high rain days) |
            | 85001 | Phoenix, AZ | Dry (low rain days) |
            | 10001 | New York, NY | Moderate |
            | 98101 | Seattle, WA | Wet |
            | 33101 | Miami, FL | Wet (summer storms) |
            """)

    # Footer
    st.divider()
    st.caption(f"Data source: NOAA Climate Data Online | Current threshold: ≥{format_threshold(threshold)} per day")


if __name__ == "__main__":
    main()
