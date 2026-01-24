"""
NOAA Weather Day Analysis Web Application

Flask application for analyzing historical rainfall data to support
construction contract weather day allowances.
"""

import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, session
from dotenv import load_dotenv
import io

from noaa_api import NOAAClient
from geocoder import ZipCodeGeocoder, get_coordinates
from data_processor import process_precipitation_data
from report_generator import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Enable debug mode for NOAA API calls
NOAA_DEBUG = os.environ.get("NOAA_DEBUG", "true").lower() == "true"

# Time period configurations
TIME_PERIODS = {
    "1yr": {"years": 1, "name": "1-Year", "min_data_years": 1},
    "2yr": {"years": 2, "name": "2-Year", "min_data_years": 2},
    "5yr": {"years": 5, "name": "5-Year", "min_data_years": 3},
    "10yr": {"years": 10, "name": "10-Year", "min_data_years": 6},
}


def get_analysis_years(period: str) -> tuple:
    """Get start and end years for analysis period."""
    current_year = datetime.now().year
    years_back = TIME_PERIODS.get(period, TIME_PERIODS["5yr"])["years"]

    # Use previous complete year as end year
    end_year = current_year - 1
    start_year = end_year - years_back + 1

    return start_year, end_year


@app.route("/")
def index():
    """Render the main application page."""
    return render_template("index.html", periods=TIME_PERIODS)


@app.route("/api/validate-token", methods=["POST"])
def validate_token():
    """Validate NOAA API token."""
    data = request.get_json()
    token = data.get("token", "").strip()

    if not token:
        return jsonify({"valid": False, "error": "Token is required"})

    try:
        client = NOAAClient(token, debug=NOAA_DEBUG)
        is_valid = client.validate_token()

        if is_valid:
            session["noaa_token"] = token
            return jsonify({"valid": True})
        else:
            return jsonify({"valid": False, "error": "Invalid token"})

    except ConnectionError as e:
        return jsonify({"valid": False, "error": str(e)})
    except Exception as e:
        return jsonify({"valid": False, "error": f"Validation failed: {str(e)}"})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Run precipitation analysis for a zip code."""
    data = request.get_json()

    zip_code = data.get("zip_code", "").strip()
    token = data.get("token") or session.get("noaa_token")
    periods = data.get("periods", ["5yr"])

    # Validate inputs
    if not zip_code:
        return jsonify({"success": False, "error": "Zip code is required"}), 400

    if not token:
        return jsonify({"success": False, "error": "NOAA API token is required"}), 400

    geocoder = ZipCodeGeocoder()
    if not geocoder.validate_zip_code(zip_code):
        return jsonify({"success": False, "error": "Invalid zip code format"}), 400

    try:
        # Step 1: Geocode zip code
        location = get_coordinates(zip_code)
        if not location:
            return jsonify({
                "success": False,
                "error": f"Could not find coordinates for zip code {zip_code}"
            }), 400

        # Step 2: Initialize NOAA client
        client = NOAAClient(token, debug=NOAA_DEBUG)
        logger.info(f"Analyzing zip code: {zip_code}, location: {location['full_location']}")

        # Step 3: Find nearest weather station
        # Use the longest requested period to find a station with sufficient data
        max_years = max(TIME_PERIODS[p]["years"] for p in periods if p in TIME_PERIODS)
        current_year = datetime.now().year
        end_year = current_year - 1
        start_year = end_year - max_years + 1

        station = client.find_nearest_station(
            location["latitude"],
            location["longitude"],
            start_year,
            end_year
        )

        if not station:
            return jsonify({
                "success": False,
                "error": f"No weather stations with precipitation data found near {zip_code}. "
                        f"Try a nearby zip code or check that your NOAA API token is valid."
            }), 404

        logger.info(f"Selected station: {station['name']} ({station['id']})")

        # Check for data warning
        station_warning = station.get("data_warning")
        if station_warning:
            logger.warning(f"Station warning: {station_warning}")

        # Step 4: Get precipitation data and process for each period
        results = {}

        for period in periods:
            if period not in TIME_PERIODS:
                continue

            period_start, period_end = get_analysis_years(period)
            period_config = TIME_PERIODS[period]

            # Fetch precipitation data
            precip_data = client.get_precipitation_data(
                station["id"],
                f"{period_start}-01-01",
                f"{period_end}-12-31"
            )

            logger.info(f"Period {period}: Retrieved {len(precip_data)} precipitation records")

            # Process data
            analysis = process_precipitation_data(precip_data, period_start, period_end)

            logger.info(f"Period {period}: Data quality - {analysis.get('data_quality', {})}")

            # Generate HTML report
            generator = ReportGenerator(station, location, analysis, period_config["name"])
            html_report = generator.generate_html()

            results[period] = {
                "period_name": period_config["name"],
                "start_year": period_start,
                "end_year": period_end,
                "analysis": analysis,
                "html_report": html_report
            }

        return jsonify({
            "success": True,
            "location": location,
            "station": {
                "id": station["id"],
                "name": station["name"],
                "distance_miles": station.get("distance_miles"),
                "direction": station.get("direction"),
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
                "data_coverage": station.get("datacoverage"),
                "data_warning": station.get("data_warning")
            },
            "results": results
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except ConnectionError as e:
        return jsonify({"success": False, "error": str(e)}), 503
    except Exception as e:
        app.logger.error(f"Analysis error: {str(e)}")
        return jsonify({"success": False, "error": f"Analysis failed: {str(e)}"}), 500


@app.route("/api/export/<format_type>", methods=["POST"])
def export_report(format_type: str):
    """Export report in specified format."""
    if format_type not in ["excel", "csv", "pdf"]:
        return jsonify({"success": False, "error": "Invalid format"}), 400

    data = request.get_json()

    station = data.get("station", {})
    location = data.get("location", {})
    analysis = data.get("analysis", {})
    period_name = data.get("period_name", "Analysis")

    try:
        generator = ReportGenerator(station, location, analysis, period_name)

        if format_type == "excel":
            content = generator.generate_excel()
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"weather_analysis_{location.get('zip_code', 'report')}.xlsx"
        elif format_type == "csv":
            content = generator.generate_csv()
            content = content.encode("utf-8")
            mimetype = "text/csv"
            filename = f"weather_analysis_{location.get('zip_code', 'report')}.csv"
        elif format_type == "pdf":
            content = generator.generate_pdf()
            mimetype = "application/pdf"
            filename = f"weather_analysis_{location.get('zip_code', 'report')}.pdf"

        return send_file(
            io.BytesIO(content),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except ImportError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        app.logger.error(f"Export error: {str(e)}")
        return jsonify({"success": False, "error": f"Export failed: {str(e)}"}), 500


@app.route("/api/station-search", methods=["POST"])
def station_search():
    """Search for weather stations near a location."""
    data = request.get_json()

    zip_code = data.get("zip_code", "").strip()
    token = data.get("token") or session.get("noaa_token")

    if not zip_code or not token:
        return jsonify({"success": False, "error": "Zip code and token required"}), 400

    try:
        location = get_coordinates(zip_code)
        if not location:
            return jsonify({"success": False, "error": "Invalid zip code"}), 400

        client = NOAAClient(token, debug=NOAA_DEBUG)
        current_year = datetime.now().year

        station = client.find_nearest_station(
            location["latitude"],
            location["longitude"],
            current_year - 10,
            current_year - 1
        )

        if station:
            return jsonify({
                "success": True,
                "location": location,
                "station": {
                    "name": station["name"],
                    "id": station["id"],
                    "distance_miles": station.get("distance_miles"),
                    "direction": station.get("direction")
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "No stations found"
            }), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template("error.html", error="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template("error.html", error="Internal server error"), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
