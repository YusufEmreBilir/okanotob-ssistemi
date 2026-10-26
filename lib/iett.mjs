const BASE = 'https://iett.istanbul';
export const STOPS = ['209482', '209481'];
export function text(html = '') {
  return html.replace(/<[^>]*>/g, ' ').replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n)).replace(/&#x([\da-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16))).replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
}
export function parseRoutes(html) {
  return [...html.matchAll(/<a\b[^>]*href="[^\"]*hkod=([^&"\s]+)[^\"]*"[^>]*>([\s\S]*?)<\/a>/g)].map(([, code, body]) => ({ code: decodeURIComponent(code), name: text(body.match(/<p[^>]*>([\s\S]*?)<\/p>/)?.[1]) }));
}
export function parseArrivals(html, stop) {
  return [...html.matchAll(/<div class="content">([\s\S]*?)<\/div>/g)].flatMap(([, body]) => {
    const code = text(body.match(/<span[^>]*>([\s\S]*?)<\/span>/)?.[1]);
    const bold = text(body.match(/<b[^>]*>([\s\S]*?)<\/b>/)?.[1]);
    const time = bold.match(/\((\d{1,2}:\d{2})\)/)?.[1];
    const minutes = bold.match(/(\d+)\s*dk/)?.[1];
    return code && time ? [{ code, stop, time: time.padStart(5, '0'), minutes: minutes === undefined ? null : +minutes, uncertain: /\bB\b/.test(bold), destination: text(body.match(/<p[^>]*>([\s\S]*?)<b/)?.[1]) }] : [];
  });
}
export function parseSchedule(html) {
  return [...html.matchAll(/<table\b[^>]*class="line-table"[^>]*>([\s\S]*?)<\/table>/g)].map(([, table]) => {
    const origin = text(table.match(/<th[^>]*colspan="3"[^>]*>([\s\S]*?)<\/th>/)?.[1]).replace(/\s+KALKIŞ$/i, '');
    const days = [[], [], []];
    for (const [, row] of table.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
      [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].slice(0, 3).forEach(([, cell], i) => {
        const label = text(cell), time = label.match(/\b(\d{1,2}:\d{2})\b/)?.[1];
        if (time) days[i].push({ time: time.padStart(5, '0'), note: label.replace(time, '').trim() });
      });
    }
    days.forEach(day => day.sort((a, b) => a.time.localeCompare(b.time)));
    return { origin, days };
  });
}
export function istanbulNow(date = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Istanbul', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date).map(p => [p.type, p.value]));
  return { time: `${parts.hour}:${parts.minute}`, day: parts.weekday === 'Sat' ? 1 : parts.weekday === 'Sun' ? 2 : 0 };
}
export function nextDeparture(schedule, now = istanbulNow()) {
  // A terminal departure is usable as a campus time only when Okan is the origin.
  const campus = schedule.find(s => /OKAN/i.test(s.origin));
  return campus?.days[now.day].find(s => s.time >= now.time) ?? null;
}
const cache = new Map();
async function request(path, { ttl = 30000, form } = {}) {
  const key = path + (form ? JSON.stringify(form) : '');
  const old = cache.get(key);
  if (old && Date.now() - old.at < ttl) return old.value;
  const response = await fetch(BASE + path, { signal: AbortSignal.timeout(12000), headers: { 'User-Agent': 'OkanDurak/1.0', ...(form ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}) }, ...(form ? { method: 'POST', body: new URLSearchParams(form) } : {}) });
  if (!response.ok) throw new Error(`İETT servisi yanıt vermedi (${response.status})`);
  const value = await response.text();
  cache.set(key, { at: Date.now(), value });
  return value;
}
export async function getBoard() {
  const stopResults = await Promise.all(STOPS.map(async stop => {
    const [routes, arrivals] = await Promise.allSettled([
      request(`/tr/RouteStationAgent/GetRouteByStation?dcode=${stop}&langid=1`, { ttl: 300000 }).then(JSON.parse).then(r => { const routes = parseRoutes(r.html ?? ''); if (!routes.length) throw new Error('Durak hat listesi boş'); return routes; }),
      request(`/tr/RouteStation/GetStationInfo?dcode=${stop}&langid=1`).then(html => { if (!/line-list|departure-times-header/.test(html)) throw new Error('Beklenmeyen durak yanıtı'); return parseArrivals(html, stop); })
    ]);
    return { stop, routes: routes.status === 'fulfilled' ? routes.value : [], arrivals: arrivals.status === 'fulfilled' ? arrivals.value : [], error: routes.status === 'rejected' || arrivals.status === 'rejected' };
  }));
  const codes = new Map();
  for (const s of stopResults) for (const r of s.routes) {
    const existing = codes.get(r.code);
    if (existing) existing.stops.push(s.stop); else codes.set(r.code, { ...r, stops: [s.stop] });
  }
  if (!codes.size) throw new Error('İETT durak verisine ulaşılamıyor. Lütfen biraz sonra tekrar deneyin.');
  const routes = await Promise.all([...codes.values()].map(async r => {
    const [schedule, status] = await Promise.allSettled([
      request('/tr/RouteStation/GetScheduledDepartureTimes', { ttl: 300000, form: { hCode: r.code, lngid: '1' } }).then(parseSchedule).then(s => { if (!s.length) throw new Error('Tarife alınamadı'); return s; }),
      request(`/tr/RouteStation/GetLineStatus?rcode=${encodeURIComponent(r.code)}`).then(JSON.parse).then(s => { if (!Array.isArray(s)) throw new Error('Duyuru alınamadı'); return s.map(text).filter(Boolean); })
    ]);
    const notices = status.status === 'fulfilled' ? status.value : [];
    return { ...r, schedule: schedule.status === 'fulfilled' ? schedule.value : [], scheduleAvailable: schedule.status === 'fulfilled', statusAvailable: status.status === 'fulfilled', notices,
      cancellation: status.status === 'rejected' ? 'unknown' : notices.some(n => /iptal|yapılama|yapilama|hizmet verem/i.test(n)) ? 'notice' : 'none',
      arrivals: stopResults.flatMap(s => s.arrivals.filter(a => a.code === r.code)).sort((a, b) => a.time.localeCompare(b.time)) };
  }));
  return { updatedAt: new Date().toISOString(), partial: stopResults.some(s => s.error) || routes.some(r => !r.scheduleAvailable || !r.statusAvailable), stops: stopResults.map(s => ({ code: s.stop, available: !s.error })), routes: routes.sort((a, b) => a.code.localeCompare(b.code, 'tr', { numeric: true })), source: BASE };
}
