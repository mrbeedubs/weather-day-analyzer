import unittest
from pathlib import Path
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch, Mock
from openpyxl import load_workbook
from data_processor import PrecipitationProcessor
from report_generator import ReportGenerator
from noaa_api import NOAAClient
from geocoder import ZipCodeGeocoder
from streamlit.testing.v1 import AppTest

class WeatherTests(unittest.TestCase):
    def test_coverage_quality_and_invalid_records(self):
        records = [{'date': '2024-01-01', 'value': 0.3},
                   {'date': '2024-01-02', 'value': 1, 'attributes': ',X,S,'},
                   {'date': '2024-01-03', 'value': -9999},
                   {'date': '2024-01-04', 'value': 0, 'attributes': 'P,,S,'},
                   {'date': 'bad', 'value': 1},
                   {'date': '2023-01-01', 'value': 1}]
        a = PrecipitationProcessor(records, 2024, 2024, 0.25).get_analysis_summary()
        self.assertEqual(a['data_quality']['data_coverage_percent'], 0.3)
        self.assertEqual(a['monthly_averages'][1], (1.0, True))
        self.assertEqual(a['monthly_rain_days'][2024][2], None)

    def test_threshold_boundaries_and_all_export_labels(self):
        day = date(2025, 1, 1)
        records = [{'date': str(day + timedelta(days=i)), 'value': 0} for i in range(365)]
        records[0]['value'] = 0.25
        records[1]['value'] = 0.249
        a = PrecipitationProcessor(records, 2025, 2025, 0.25).get_analysis_summary()
        self.assertEqual(a['yearly_totals'][2025], 1)
        self.assertEqual(a['data_quality']['data_coverage_percent'], 100)
        g = ReportGenerator({'id': 'TEST', 'name': 'TEST'}, {'zip_code': '29708'}, a, '1-Year')
        self.assertIn('0.25', g.generate_csv().splitlines()[0])
        self.assertIn('0.25', g.generate_html())
        self.assertIn('0.25', load_workbook(BytesIO(g.generate_excel())).active['A1'].value)
        self.assertTrue(g.generate_pdf().startswith(b'%PDF'))

    def test_http_errors_do_not_become_missing_data(self):
        for status in [403, 429, 500]:
            client = NOAAClient('dummy')
            client.session.get = Mock(return_value=Mock(status_code=status, text='failure'))
            with patch('noaa_api.time.sleep'), patch.object(client, '_rate_limit'):
                with self.assertRaises(ConnectionError):
                    client.get_precipitation_data('TEST', '2025-01-01', '2025-12-31')

    def test_empty_success_is_not_http_failure(self):
        client = NOAAClient('dummy')
        client.session.get = Mock(return_value=Mock(status_code=200, json=lambda: {}))
        self.assertEqual(client.get_precipitation_data('TEST', '2025-01-01', '2025-12-31'), [])

    def test_geocode_cache(self):
        import geocoder
        geocoder._GEOCODE_CACHE.clear()
        with patch.object(ZipCodeGeocoder, '_geocode_census', return_value=None), patch.object(ZipCodeGeocoder, '_geocode_nominatim', return_value={'latitude': 35, 'longitude': -81}) as fallback:
            ZipCodeGeocoder().geocode('29708')
            ZipCodeGeocoder().geocode('29708')
            self.assertEqual(fallback.call_count, 1)

    def test_streamlit_rerun_retains_results(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'))
        at.secrets['NOAA_API_KEY'] = 'dummy'
        at.run()
        self.assertEqual(len(at.exception), 0)
        with patch.object(ZipCodeGeocoder, 'geocode', return_value={'latitude':35., 'longitude':-81., 'full_location':'TEST', 'zip_code':'29708'}), patch.object(NOAAClient, 'find_nearest_station', return_value={'id':'TEST', 'name':'TEST'}), patch.object(NOAAClient, 'get_precipitation_data', return_value=[{'date':'2025-01-01', 'value':0.3}]):
            at.text_input[0].set_value('29708'); at.selectbox[0].set_value(0.25); at.run()
            at.button[0].click(); at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(len(at.error), 0)
            self.assertEqual(len(at.dataframe), 1)
            at.run()
            self.assertEqual(len(at.dataframe), 1)

if __name__ == '__main__':
    unittest.main()
