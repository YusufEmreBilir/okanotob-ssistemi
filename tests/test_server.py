import unittest
from unittest.mock import patch
import server

class ScheduleTests(unittest.TestCase):
    def test_filters_routes_not_visiting_campus_and_deduplicates(self):
        line={'code':'130H','routeCodes':['130H_D_D6194'],'directions':{}}
        base={'DT':'13:25','SYON':'D','SGUNTIPI':'I','SGUZERAH':'130H_D_D6194'}
        rows=[base,base,{**base,'SGUZERAH':'130H_D_D0'},{**base,'DT':'10:99'},{**base,'SGUNTIPI':'?'}]
        actual=server.normalize(line,rows)
        self.assertEqual(len(actual),1)
        self.assertEqual(actual[0]['minutes'],805)

    def test_failed_refresh_retains_data_but_marks_stale(self):
        server.CACHE.clear()
        with patch('server.time.time',return_value=1):
            first=server.cached('test',lambda:[{'time':'10:00'}],60)
        with patch('server.time.time',return_value=100):
            failed=server.cached('test',lambda:1/0,60)
        self.assertTrue(failed['stale'])
        self.assertIsNotNone(failed['error'])
        self.assertEqual(first['data'],failed['data'])

    def test_first_failure_does_not_claim_empty_success(self):
        server.CACHE.clear()
        result=server.cached('missing',lambda:1/0,60)
        self.assertIsNotNone(result['error'])
        self.assertIsNone(result['updatedAt'])
        self.assertFalse(result['stale'])

    def test_unsupported_km28_variant_is_excluded(self):
        line=next(l for l in server.LINES if l['code']=='KM28')
        base={'DT':'09:00','SYON':'D','SGUNTIPI':'I','SGUZERAH':'KM28_D_D0'}
        self.assertEqual(len(server.normalize(line,[base,{**base,'SGUZERAH':'KM28_D_OTHER'}])),1)

    def test_extended_service_times(self):
        self.assertEqual(server.minutes('25:15'),1515)
        self.assertIsNone(server.minutes('24:99'))
        self.assertIsNone(server.minutes('garbage'))

if __name__=='__main__':unittest.main()
