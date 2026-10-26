import { istanbulNow, nextDeparture } from '/lib/iett.mjs';
const $ = s => document.querySelector(s);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const pretty = s => s.toLocaleLowerCase('tr-TR').replace(/(^|[\s/\-])\p{L}/gu, c => c.toLocaleUpperCase('tr-TR'));
let board, filter = 'all', query = '', busy = false, selected, day = istanbulNow().day;
let favorites;
try { favorites = new Set(JSON.parse(localStorage.getItem('okan-favorites') || '[]')); } catch { favorites = new Set(); }
function clock() {
  const now = new Date();
  const time = new Intl.DateTimeFormat('tr-TR', { timeZone:'Europe/Istanbul', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23' }).format(now).split(':');
  $('#clock').innerHTML = `${time[0]}:${time[1]}<span>${time[2]}</span>`;
  $('#date').textContent = new Intl.DateTimeFormat('tr-TR', { timeZone:'Europe/Istanbul', day:'numeric', month:'long', weekday:'long' }).format(now);
}
function upcoming(r) {
  const elapsed = (Date.now() - new Date(board.updatedAt)) / 60000;
  const arrival = r.arrivals.find(a => a.minutes !== null && a.minutes >= elapsed && !a.uncertain);
  if (arrival && elapsed < 2) return { ...arrival, minutes: Math.max(0, Math.ceil(arrival.minutes - elapsed)), kind: 'Tahmini durak varışı' };
  const planned = nextDeparture(r.schedule);
  if (planned) {
    const now = istanbulNow().time.split(':').map(Number), parts = planned.time.split(':').map(Number);
    return { ...planned, minutes: parts[0] * 60 + parts[1] - now[0] * 60 - now[1], kind:'Planlı kampüs kalkışı' };
  }
  return null;
}
function render() {
  if (!board) return;
  const routes = board.routes.filter(r => (!query || `${r.code} ${r.name}`.toLocaleLowerCase('tr-TR').includes(query)) && (filter !== 'favorites' || favorites.has(r.code)) && (filter !== 'soon' || (upcoming(r)?.minutes ?? Infinity) <= 60));
  $('#route-count').textContent = board.routes.length;
  $('#routes').innerHTML = routes.length ? routes.map(r => {
    const next = upcoming(r), warning = r.cancellation === 'notice', unknown = !r.statusAvailable;
    return `<article class="route"><div class="route-main" role="button" tabindex="0" data-route="${escape(r.code)}" aria-label="${escape(r.code)} tüm sefer saatleri" aria-haspopup="dialog"><div class="route-title"><span class="route-badge">${escape(r.code)}</span><div><div class="route-name">${escape(pretty(r.name))}</div><div class="route-meta"><b>İETT</b><span>${r.stops.length === 2 ? 'Her iki durakta' : 'Kampüs çıkış durağı'}</span></div></div></div><div><div class="arrival-time">${next ? escape(next.time) : '—'}${next ? `<small>${next.minutes === 0 ? 'Şimdi' : `${next.minutes} dk`}</small>` : ''}</div><div class="arrival-label">${next ? escape(next.kind) : r.scheduleAvailable ? 'Durak tahmini yok' : 'Saatler alınamadı'}</div></div><div class="route-status"><span class="status-pill ${warning ? 'warning' : unknown ? 'unknown' : ''}">${warning ? 'İptal duyurusu var' : unknown ? 'Durum bilinmiyor' : 'İptal duyurusu yok'}</span><div class="status-caption">${r.notices.length ? `${r.notices.length} hat duyurusu · Detayları gör` : 'Hat duyurularına göre'}</div></div><span class="chevron">↗</span></div><div class="route-bottom"><span>Tüm sefer saatleri <span aria-hidden="true">↗</span></span><button class="favorite ${favorites.has(r.code) ? 'selected' : ''}" data-favorite="${escape(r.code)}" aria-label="${escape(r.code)} ${favorites.has(r.code) ? 'favorilerden çıkar' : 'favorilere ekle'}" aria-pressed="${favorites.has(r.code)}">${favorites.has(r.code) ? '★' : '☆'}</button></div></article>`;
  }).join('') : '<div class="empty">Bu görünümde hat bulunamadı. Filtreyi veya arama metnini değiştirebilirsin.</div>';
}
async function refresh() {
  if (busy) return;
  busy = true; $('#refresh').disabled = true;
  try {
    const response = await fetch('/api/board', { signal: AbortSignal.timeout(45000) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Veri alınamadı.');
    board = data; render();
    $('#notice').hidden = !data.partial;
    $('#notice').textContent = 'Bazı İETT servislerine erişilemiyor. Eksik saat veya iptal bilgileri bilinmiyor olarak gösteriliyor.';
    $('#updated').textContent = `Son güncelleme ${new Intl.DateTimeFormat('tr-TR', { timeZone:'Europe/Istanbul', hour:'2-digit', minute:'2-digit', second:'2-digit' }).format(new Date(data.updatedAt))}`;
    $('#connection-dot').classList.add('connected');
    if ($('#detail').open && selected) { selected = board.routes.find(r => r.code === selected.code) || selected; renderDetail(); }
  } catch (e) {
    $('#notice').hidden = false;
    $('#notice').textContent = `${e.name === 'TimeoutError' ? 'İETT bağlantısı zaman aşımına uğradı.' : e.message} ${board ? 'Son alınan veriler gösteriliyor; güncel olmayabilir.' : 'Yenile düğmesiyle tekrar deneyebilirsin.'}`;
    $('#connection-dot').classList.remove('connected');
    $('#updated').textContent = board ? 'Bağlantı kesildi · Son alınan veriler' : 'İETT bağlantısı kurulamadı';
    if (!board) $('#routes').innerHTML = '<div class="empty">Güncel hat verisi alınamadı. Yenile ile tekrar dene.</div>';
  } finally { busy = false; $('#refresh').disabled = false; }
}
function renderDetail() {
  const r = selected, now = istanbulNow();
  $('#detail-content').innerHTML = `<div class="detail-heading"><span class="route-badge">${escape(r.code)}</span><h2>${escape(pretty(r.name))}</h2></div><p class="detail-note">Bu saatler <strong>ilk duraktan kalkış</strong> tarifesidir. Kampüsten başlayan yönde kampüs kalkışını gösterir; ara duraklarda varış saati değildir. Resmî tatillerde tarife değişebilir.</p>${r.notices.map(n => `<div class="notice-item">${escape(n)}</div>`).join('')}${!r.statusAvailable ? '<div class="notice-item">İptal / duyuru bilgisi alınamadı.</div>' : ''}<div class="day-tabs" role="group" aria-label="Tarife günü">${['Hafta içi', 'Cumartesi', 'Pazar'].map((name, i) => `<button data-day="${i}" class="${i === day ? 'active' : ''}" aria-pressed="${i === day}">${name}${now.day === i ? ' · Bugün' : ''}</button>`).join('')}</div>${r.schedule.length ? r.schedule.map(s => {
    let highlighted = false;
    return `<section class="schedule-block"><h3>↗ ${escape(pretty(s.origin))} kalkış</h3><div class="times">${s.days[day].map(t => {
      const past = day === now.day && t.time < now.time, next = day === now.day && !past && !highlighted;
      if (next) highlighted = true;
      return `<span class="time ${past ? 'past' : next ? 'next' : ''}">${escape(t.time)}${t.note ? `<small>${escape(t.note)}</small>` : ''}</span>`;
    }).join('') || '<p>Bu gün için sefer yayımlanmamış.</p>'}</div></section>`;
  }).join('') : '<div class="empty">Bu hattın sefer tarifesi şu an alınamıyor.</div>'}<p class="schedule-legend">Saatlerin yanındaki işaretler özel güzergâhları belirtir; iptal anlamına gelmez. Açıklamalar için İETT hat sayfasını inceleyebilirsin. İptal bilgisi hat duyurularından alınır; tek tek seferler için kesin iptal doğrulaması sunulmaz.</p><a class="dialog-source" href="https://iett.istanbul/RouteDetail?hkod=${encodeURIComponent(r.code)}" target="_blank" rel="noopener noreferrer">İETT’de hattı ve güzergâh notlarını aç ↗</a>`;
}
$('#routes').addEventListener('click', e => {
  const favorite = e.target.closest('[data-favorite]');
  if (favorite) {
    const code = favorite.dataset.favorite; favorites.has(code) ? favorites.delete(code) : favorites.add(code);
    try { localStorage.setItem('okan-favorites', JSON.stringify([...favorites])); } catch { /* Favorites continue in memory when storage is blocked. */ }
    render(); return;
  }
  const route = e.target.closest('.route'); const code = route?.querySelector('[data-route]')?.dataset.route;
  if (code) { selected = board.routes.find(r => r.code === code); day = istanbulNow().day; renderDetail(); $('#detail').showModal(); }
});
$('#routes').addEventListener('keydown', e => { if (e.target.matches('[data-route]') && ['Enter', ' '].includes(e.key)) { e.preventDefault(); e.target.click(); } });
$('#close').onclick = () => $('#detail').close();
$('#detail').addEventListener('click', e => { if (e.target === $('#detail')) { const rect = e.target.getBoundingClientRect(); if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) e.target.close(); } const tab = e.target.closest('[data-day]'); if (tab) { day = +tab.dataset.day; renderDetail(); } });
document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); }); render(); });
$('#search').oninput = e => { query = e.target.value.toLocaleLowerCase('tr-TR').trim(); render(); };
document.addEventListener('keydown', e => { if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName) && !$('#detail').open) { e.preventDefault(); $('#search').focus(); } });
$('#refresh').onclick = refresh;
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
clock(); setInterval(clock, 1000); setInterval(() => { if (!document.hidden) refresh(); }, 30000); setInterval(render, 15000); refresh();
