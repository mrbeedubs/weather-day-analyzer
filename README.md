# Weather Day Analyzer

A professional web application for analyzing historical rainfall data from NOAA weather stations to support construction contract weather day allowances.

## Features

- **Zip Code Search**: Find the nearest NOAA weather station to any US location
- **Multiple Time Periods**: Analyze 1, 2, 5, or 10 years of historical data
- **Rain Day Analysis**: Count days with ≥0.5" precipitation per month
- **Professional Reports**: Generate reports suitable for contract documentation
- **Export Options**: Download reports in Excel, CSV, or PDF format
- **Data Quality Indicators**: Clear marking of missing or incomplete data

## Quick Start

### 1. Get a NOAA API Key (Free)

1. Visit [NOAA CDO Token Request](https://www.ncdc.noaa.gov/cdo-web/token)
2. Enter your email address
3. Check your inbox for the API token (usually arrives within minutes)
4. Save the token - you'll need it to use this application

### 2. Run Locally

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/weather-day-analyzer.git
cd weather-day-analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create secrets file
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and add your NOAA API key

# Run the app
streamlit run streamlit_app.py
```

Open http://localhost:8501 in your browser.

---

## Deployment to Streamlit Cloud

### Step 1: Prepare Your Repository

1. **Create a GitHub repository** (if you haven't already)
   - Go to https://github.com/new
   - Name it `weather-day-analyzer`
   - Make it Public (required for free Streamlit Cloud)

2. **Push your code to GitHub**
   ```bash
   cd weather-day-analyzer
   git init
   git add .
   git commit -m "Initial commit - Weather Day Analyzer"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/weather-day-analyzer.git
   git push -u origin main
   ```

### Step 2: Deploy to Streamlit Cloud

1. **Go to Streamlit Cloud**: https://share.streamlit.io/

2. **Sign in with GitHub**

3. **Click "New app"**

4. **Configure your app**:
   - Repository: `YOUR_USERNAME/weather-day-analyzer`
   - Branch: `main`
   - Main file path: `streamlit_app.py`

5. **Add your NOAA API key as a secret**:
   - Click "Advanced settings"
   - In the "Secrets" section, add:
     ```toml
     NOAA_API_KEY = "your-actual-noaa-api-key"
     ```
   - Click "Save"

6. **Click "Deploy!"**

Your app will be live at: `https://YOUR_APP_NAME.streamlit.app`

### Step 3: Share Your App

Once deployed, you can share the URL with anyone. They'll be able to:
- Enter any US zip code
- Analyze historical precipitation data
- Download professional reports

---

## Configuration

### Environment Variables / Secrets

| Variable | Description | Required |
|----------|-------------|----------|
| `NOAA_API_KEY` | Your NOAA Climate Data Online API token | Yes |

### Streamlit Cloud Secrets

In Streamlit Cloud, add secrets via the app dashboard:
1. Go to your app's settings
2. Click "Secrets"
3. Add your NOAA_API_KEY

```toml
NOAA_API_KEY = "your-noaa-api-key-here"
```

---

## Usage Guide

### Analyzing a Location

1. **Enter a Zip Code**: Type any 5-digit US zip code in the sidebar
2. **Select Time Periods**: Choose which historical periods to analyze (1yr, 2yr, 5yr, 10yr)
3. **Click "Analyze Precipitation Data"**
4. **Review Results**: View rain day counts by month and year
5. **Export Reports**: Download Excel, CSV, or PDF reports

### Understanding the Report

- **Rain Days**: Days with ≥0.5 inches of precipitation
- **~** prefix: Indicates approximate average (some years missing data)
- **-**: No data available for that period
- **Monthly counts**: Number of rain days in each month
- **TOTAL**: Sum of rain days for the year

### Sample Zip Codes

| Zip Code | Location | Climate |
|----------|----------|---------|
| 97401 | Eugene, OR | Wet (high rain days) |
| 85001 | Phoenix, AZ | Dry (low rain days) |
| 10001 | New York, NY | Moderate |
| 98101 | Seattle, WA | Wet |
| 33101 | Miami, FL | Wet (summer storms) |

---

## For Construction Professionals

This tool is designed to support documentation for construction contract weather day allowances. The reports are:

- **Professional**: Clean formatting suitable for contracts
- **Defensible**: Sourced from official NOAA weather stations
- **Transparent**: Clear marking of data gaps
- **Standard**: Uses calendar year layout (January-December)

### Typical Use Cases

- Document historical weather patterns for bid preparation
- Support weather delay claims with official data
- Establish baseline weather expectations for contracts
- Provide evidence for contract negotiations

---

## Technical Details

### Data Sources

- **Weather Data**: NOAA Climate Data Online (CDO)
- **Dataset**: Global Historical Climatology Network Daily (GHCND)
- **Geocoding**: US Census Bureau / OpenStreetMap

### Station Selection Logic

The application prioritizes weather stations by:
1. **Station Type**: Official weather stations (airports) over community stations
2. **Data Availability**: Verified precipitation data for requested period
3. **Distance**: Proximity to the specified zip code
4. **Coverage**: Percentage of days with recorded data

### Project Structure

```
weather-day-analyzer/
├── streamlit_app.py      # Streamlit web application
├── noaa_api.py           # NOAA API client
├── geocoder.py           # Zip code geocoding
├── data_processor.py     # Precipitation data processing
├── report_generator.py   # Report generation (Excel/CSV/PDF)
├── requirements.txt      # Python dependencies
├── .streamlit/
│   ├── config.toml       # Streamlit configuration
│   └── secrets.toml.template  # Secrets template
├── .gitignore
└── README.md
```

---

## Troubleshooting

### "Invalid token" error
- Ensure you copied the entire token from the NOAA email
- Check for leading/trailing spaces
- Request a new token if it's been more than 30 days

### "No stations found" error
- Try a nearby zip code
- Some remote areas may lack weather stations
- The application searches within 50 miles

### Missing data for recent months
- NOAA data has approximately 2-3 month lag
- Current year data may be incomplete

### Slow response times
- First requests may take longer (API warm-up)
- Large date ranges (10yr) require more API calls
- Results are cached for 1 hour to improve subsequent requests

### Rate limiting
- NOAA API allows ~10,000 requests per day
- The application implements automatic rate limiting
- If you hit limits, wait a few minutes and try again

---

## API Rate Limits

NOAA CDO API has the following limits:
- 5 requests per second
- 10,000 requests per day

The application handles rate limiting automatically with:
- Request throttling (max 4 requests/second)
- Retry logic for rate-limited responses
- Caching to reduce duplicate API calls

---

## License

This project is provided for educational and professional use. NOAA data is public domain.

---

## Support

For issues or feature requests, please open an issue on GitHub.

## Acknowledgments

- NOAA Climate Data Online for providing historical weather data
- US Census Bureau for geocoding services
- Streamlit for the excellent web framework
