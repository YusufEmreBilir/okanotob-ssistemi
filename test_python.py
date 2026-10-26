from datetime import datetime
import unittest

from iett_client import ISTANBUL, calculated_arrivals, day_index, merge_arrivals, parse_arrivals, parse_campus_profiles, parse_default_profiles, parse_routes, parse_schedule, parse_stop_notices, upcoming

class IettTests(unittest.TestCase):
    def test_stop_routes_decode_entities(self):
        html = '<a href="/RouteDetail?hkod=KM28&amp;x=1"><span>KM28</span><p>OKAN &#220;NİVERSİTESİ - METRO</p></a>'
        self.assertEqual(parse_routes(html), [dict(code='KM28', name='OKAN ÜNİVERSİTESİ - METRO')])

    def test_live_stop_predictions_preserve_direction(self):
        html = '<div class="content"><span>133GP</span><p>G&#214;&#199;BEYLİ - KARTAL <b>(15:24) 8 dk</b></p></div>'
        a = parse_arrivals(html, '209482')[0]
        self.assertEqual((a['time'], a['minutes'], a['destination'], a['stop']), ('15:24', 8, 'GÖÇBEYLİ - KARTAL', '209482'))
        self.assertFalse(a['uncertain'])

    def test_schedule_keeps_empty_columns_and_route_markers(self):
        html = '<table class="line-table"><th colspan="3">OKAN ÜNİVERSİTESİ KALKIŞ</th><tr><td>08:05 -1</td><td></td><td style="color:red">13:00</td></tr></table>'
        s = parse_schedule(html)[0]
        self.assertEqual(s['origin'], 'OKAN ÜNİVERSİTESİ')
        self.assertEqual(s['days'], [[dict(time='08:05', note='-1')], [], [dict(time='13:00', note='')]])

    def test_live_prediction_prioritized_and_countdown_decreases(self):
        a = dict(time='15:25', minutes=9, observed_at=1000, uncertain=False)
        route = dict(arrivals=[a], schedule=[dict(origin='OKAN', days=[[dict(time='15:00')], [], []])])
        result = upcoming(route, datetime(2026, 10, 26, 14, 0, tzinfo=ISTANBUL), 1060)[0]
        self.assertTrue(result['live'])
        self.assertEqual(result['minutes'], 8)

    def test_stale_predictions_never_used_as_live(self):
        route = dict(arrivals=[dict(time='15:25', minutes=9, observed_at=1000, uncertain=False)], schedule=[])
        self.assertEqual(upcoming(route, stamp=1121), [])

    def test_b_marker_is_not_claimed_as_live(self):
        a = parse_arrivals('<div class="content"><span>KM28</span><p>OKAN - METRO <b>(15:25) 9 dk B</b></p></div>', '209482')[0]
        self.assertFalse(upcoming(dict(arrivals=[a]), stamp=a['observed_at'])[0]['live'])

    def test_other_terminal_time_is_not_campus_arrival(self):
        route = dict(arrivals=[], schedule=[dict(origin='KARTAL', days=[[dict(time='16:00')], [], []])])
        self.assertEqual(upcoming(route, datetime(2026, 10, 26, 15, 0, tzinfo=ISTANBUL)), [])

    def test_campus_next_time_and_end_of_day(self):
        route = dict(arrivals=[], schedule=[dict(origin='OKAN ÜNİVERSİTESİ', days=[[dict(time='15:25')], [], []])])
        now = datetime(2026, 10, 26, 15, 0, tzinfo=ISTANBUL)
        self.assertEqual(upcoming(route, now)[0]['minutes'], 25)
        self.assertEqual(upcoming(route, now.replace(hour=23)), [])

    def test_weekend(self):
        self.assertEqual(day_index(datetime(2026, 10, 24, tzinfo=ISTANBUL)), 1)
        self.assertEqual(day_index(datetime(2026, 10, 25, tzinfo=ISTANBUL)), 2)
        self.assertEqual(day_index(datetime(2026, 10, 26, tzinfo=ISTANBUL)), 0)

    def test_arrival_with_minutes_only_and_extra_css_classes(self):
        html = "<div class='content prediction'><span>KM28</span><p>OKAN - METRO <b>9 dk</b></p></div>"
        a = parse_arrivals(html, '209482')[0]
        self.assertEqual(a['minutes'], 9)
        self.assertRegex(a['time'], r'^\d{2}:\d{2}$')

    def test_arrival_with_clock_only_gets_remaining_minutes(self):
        from unittest.mock import patch
        observed = datetime(2026, 10, 26, 15, 0, tzinfo=ISTANBUL).timestamp()
        with patch('iett_client.time.time', return_value=observed):
            a = parse_arrivals('<div class="content"><span>KM28</span><p>OKAN - METRO <b>(15:08)</b></p></div>', '209482')[0]
        self.assertEqual(a['minutes'], 8)
        self.assertTrue(upcoming(dict(arrivals=[a]), stamp=observed)[0]['live'])

    def test_secondary_source_fills_missing_route_without_overwriting(self):
        primary = [dict(code='KM28', stop='209482', destination='METRO', minutes=9)]
        backup = [dict(code='KM28', stop='209482', destination='METRO', minutes=7),
                  dict(code='132D', stop='209482', destination='KARTAL', minutes=10)]
        combined = merge_arrivals(primary, backup)
        self.assertEqual(len(combined), 2)
        self.assertEqual(combined[0]['minutes'], 9)
        self.assertEqual(combined[1]['code'], '132D')

    def test_stop_warning_text_is_available_outside_route_detail(self):
        html = "<div class='duyuru-scroll'><p><b>132D</b>: Trafik nedeniyle 20 dakika rötar.</p></div>"
        self.assertEqual(parse_stop_notices(html), {'132D': ['Trafik nedeniyle 20 dakika rötar.']})

    def profile(self, **changes):
        profile = dict(origin='TERMİNAL', destination='KARTAL', branch='TEST_G_D1', stop='209482',
                       position=2, stop_count=5, days=[[dict(time='15:00', note='')], [], []])
        return dict(profile, **changes)

    def test_calculated_arrival_uses_travel_offset_and_is_labeled(self):
        route = dict(campus_profiles=[self.profile()], duration_minutes=40)
        now = datetime(2026, 10, 26, 15, 10, tzinfo=ISTANBUL)
        entry = calculated_arrivals(route, now)[0]
        self.assertEqual((entry['time'], entry['minutes'], entry['travel_minutes']), ('15:20', 10, 20))
        self.assertEqual(entry['margin'], 6)
        self.assertTrue(entry['estimated'])
        self.assertFalse(entry['live'])

    def test_special_weekday_service_looks_ahead_across_weekend(self):
        route = dict(campus_profiles=[self.profile()], duration_minutes=40)
        now = datetime(2026, 10, 23, 23, 0, tzinfo=ISTANBUL)
        entry = calculated_arrivals(route, now)[0]
        self.assertEqual(entry['arrival_date'], '2026-10-26')
        self.assertEqual(entry['days_ahead'], 3)

    def test_previous_day_departure_can_arrive_after_midnight(self):
        p = self.profile(days=[[dict(time='23:50', note='')], [], []])
        entry = calculated_arrivals(dict(campus_profiles=[p], duration_minutes=40), datetime(2026, 10, 27, 0, 0, tzinfo=ISTANBUL))[0]
        self.assertEqual((entry['time'], entry['arrival_date']), ('00:10', '2026-10-27'))

    def test_campus_terminal_has_zero_travel_offset(self):
        route = dict(campus_profiles=[self.profile(position=0)], duration_minutes=40)
        entry = calculated_arrivals(route, datetime(2026, 10, 26, 14, 50, tzinfo=ISTANBUL))[0]
        self.assertEqual((entry['time'], entry['margin'], entry['estimated']), ('15:00', 0, False))

    def test_today_main_departure_beats_tomorrow_special_route(self):
        route = dict(arrivals=[], duration_minutes=40, campus_profiles=[
            self.profile(branch='main', position=0, days=[[dict(time='16:00', note='')], [], []]),
            self.profile(branch='special', days=[[dict(time='07:00', note='')], [], []])])
        self.assertEqual(upcoming(route, datetime(2026, 10, 26, 15, 0, tzinfo=ISTANBUL))[0]['time'], '16:00')

    def test_no_invented_travel_time_if_route_duration_is_missing(self):
        self.assertEqual(calculated_arrivals(dict(campus_profiles=[self.profile()]), datetime(2026, 10, 26, 14, 0, tzinfo=ISTANBUL)), [])

    def test_depar_table_is_bound_to_its_own_stop_list(self):
        table = '<table class="line-table"><th colspan="3">TERMİNAL KALKIŞ</th><tr><td>15:00</td><td></td><td></td></tr></table>'
        html = '<div id="133P_G_D1085" class="tab-line-content"><a href="/StationDetail?dkod=111"><p>1. BAŞKA</p></a>' + table
        html += '<div id="133P_G_D1087" class="tab-line-content"><a href="/StationDetail?dkod=111"><p>1. TERMİNAL<span> - Tuzla</span></p></a><a href="/StationDetail?dkod=209482"><p>2. OKAN<span> - Tuzla</span></p></a>' + table
        profiles = parse_campus_profiles(html)
        self.assertEqual(len(profiles), 1)
        self.assertEqual((profiles[0]['branch'], profiles[0]['position'], profiles[0]['stop_count']), ('133P_G_D1087', 1, 2))

    def test_marked_special_service_not_reused_as_default_route(self):
        html = '<div class="col-md-6 col-12"><a href="/StationDetail?dkod=209482"><p>1. OKAN</p></a><a href="/StationDetail?dkod=111"><p>2. METRO</p></a>'
        schedule = dict(origin='OKAN', days=[[dict(time='08:00', note='-1'), dict(time='09:00', note='')], [], []])
        profile = parse_default_profiles(html, [schedule], 'KM28')[0]
        self.assertEqual(profile['days'][0], [dict(time='09:00', note='')])

if __name__ == '__main__':
    unittest.main()
