import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRoutes, parseArrivals, parseSchedule, nextDeparture, istanbulNow, text } from '../lib/iett.mjs';

test('İETT numeric entities and markup are decoded', () => {
  assert.equal(text('G&#214;&#199;BEYLİ <b> - KARTAL</b>'), 'GÖÇBEYLİ - KARTAL');
});
test('stop membership comes from route links', () => {
  assert.deepEqual(parseRoutes('<a href="/RouteDetail?hkod=KM28&amp;routename=x"><span>KM28</span><p>OKAN &#220;NİVERSİTESİ - METRO</p></a>'), [{ code:'KM28', name:'OKAN ÜNİVERSİTESİ - METRO' }]);
});
test('arrivals retain direction, stop and uncertain B marker', () => {
  const html = '<div class="content"><span>132D</span><p>KÖY - KARTAL <b>(15:31) 29 dk B</b></p></div>';
  assert.deepEqual(parseArrivals(html, '209482'), [{ code:'132D', stop:'209482', time:'15:31', minutes:29, uncertain:true, destination:'KÖY - KARTAL' }]);
});
test('schedule columns preserve empty cells and route markers; red is not inferred as cancellation', () => {
  const html = '<table class="line-table"><thead><th colspan="3">OKAN ÜNİVERSİTESİ KALKIŞ</th></thead><tbody><tr><td>08:05 -1</td><td></td><td style="color:red">13:00</td></tr><tr><td>09:00</td><td>10:00</td><td></td></tr></tbody></table>';
  const [s] = parseSchedule(html);
  assert.equal(s.origin,'OKAN ÜNİVERSİTESİ');
  assert.deepEqual(s.days, [[{ time:'08:05', note:'-1' },{ time:'09:00', note:'' }],[{ time:'10:00', note:'' }],[{ time:'13:00', note:'' }]]);
});
test('only campus origin departures become next campus time, never another terminal', () => {
  const schedule = [{ origin:'KARTAL', days:[[{ time:'16:00' }],[],[]] }, { origin:'OKAN ÜNİVERSİTESİ', days:[[{ time:'08:00' },{ time:'15:25' }],[],[]] }];
  assert.equal(nextDeparture(schedule, { day:0, time:'15:00' }).time,'15:25');
  assert.equal(nextDeparture(schedule, { day:0, time:'23:00' }),null);
  assert.equal(nextDeparture(schedule.slice(0,1), { day:0, time:'15:00' }),null);
});
test('Istanbul weekday and midnight use UTC+3 independently of server timezone', () => {
  assert.deepEqual(istanbulNow(new Date('2026-10-23T21:10:00Z')), { time:'00:10', day:1 });
  assert.deepEqual(istanbulNow(new Date('2026-10-25T21:10:00Z')), { time:'00:10', day:0 });
});
