# Weather Day Analyzer

Streamlit app for historical NOAA daily precipitation counts by US ZIP code. Counts support planning; they do not independently establish compensable delay or contractual weather allowances.

## Run locally

Use Python 3.12, matching the deployment environment.

```bash
git clone https://github.com/mrbeedubs/weather-day-analyzer.git
cd weather-day-analyzer
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Enter your real NOAA token in .streamlit/secrets.toml; never commit it.
python -m streamlit run streamlit_app.py
```

On Windows activate with `.venv\Scripts\activate`; copy the template manually. Streamlit reads `NOAA_API_KEY` from Streamlit secrets, not `.env`.

## Deploy and share

1. Sign into https://share.streamlit.io/ and connect your GitHub account.
2. Select repository `mrbeedubs/weather-day-analyzer`, branch `main`, entry point `streamlit_app.py`.
3. In Advanced settings select Python 3.12 and enter `NOAA_API_KEY = "actual token"` in Secrets.
4. Deploy, check logs, run the acceptance checks below, and verify viewer permissions.
5. Copy the actual URL issued by Streamlit. No deployment URL has been verified yet.

Community Cloud supports public and private repositories. Streamlit Community Cloud is free; request a NOAA token at https://www.ncei.noaa.gov/cdo-web/token. No paid hosting or custom domain is required for this deployment path. Sources checked October 14, 2026: https://docs.streamlit.io/deploy/streamlit-community-cloud and https://www.ncei.noaa.gov/cdo-web/faq.

`app.py`, `templates/`, and `.env.example` belong to an older, separate Flask implementation. They are not used by the Streamlit deployment. The Streamlit requirements intentionally exclude Flask and python-dotenv; the Flask version is not validated for deployment.

## Analysis and limitations

- Thresholds: 0.10, 0.25, 0.50, 0.75, or 1.00 inches, inclusive (≥).
- Periods: 1, 2, 5, or 10 previous calendar years; current year excluded.
- Station selection balances station type, proximity, and metadata coverage, within a 50-mile radius. It does not always select the closest station. An unverified fallback station is explicitly warned about.
- Counts represent observed valid days. Missing days are not assumed dry. Monthly and annual averages marked `~` include incomplete observations; do not treat them as full-period allowances. Annual totals with more than three wholly missing months are withheld.
- Coverage is valid daily observations divided by requested calendar days. Invalid dates/values, quality-flagged records and presumed-zero observations are excluded. Conflicting duplicate observations stop processing.
- CDO requests explicitly use standard units; the processor expects precipitation in inches. Reconcile a real CDO sample with the NOAA source before production use. Native GHCND text-file units are different and must not be fed directly into this processor.
- API errors stop analysis. A successful empty response represents unavailable observations. Cached NOAA results expire after one hour.
- NOAA throttling is shared by client instances within one Python process. It does not coordinate other apps or processes using the same token and does not enforce a daily quota.
- ZIP geocoding uses Census then Nominatim. Nominatim requests are serialized, cached and limited within one process. Do not run multiple workers against the public service without a shared limiter or another provider. Configure `NOMINATIM_URL` to switch providers. Attribution: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright.

## Verification

```bash
python -m unittest discover -s tests -v
```

Before sharing:

- Run a valid ZIP such as 29708; confirm station coordinates and distance.
- Reconcile a known NOAA station/date precipitation value and threshold count.
- Try each period and threshold; inspect missing/partial-data warnings.
- Download Excel, CSV and PDF; verify threshold labels, counts, layout and results retained after downloads.
- Test invalid ZIP, invalid token and unavailable services.
- Confirm the shared link works in a signed-out browser; check simultaneous users and Cloud logs.

Sources checked October 14, 2026:
- NOAA API and token limits: https://www.ncei.noaa.gov/cdo-web/webservices/v2
- GHCND flag definitions: https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt
- Nominatim use restrictions (aggregate application traffic maximum one request/second, attribution required): https://operations.osmfoundation.org/policies/nominatim/
- Streamlit deployment: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
