import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { getBoard } from './lib/iett.mjs';
const assets = { '/': ['public/index.html', 'text/html'], '/style.css': ['public/style.css', 'text/css'], '/app.js': ['public/app.js', 'text/javascript'], '/lib/iett.mjs': ['lib/iett.mjs', 'text/javascript'], '/favicon.svg': ['public/favicon.svg', 'image/svg+xml'] };
let pending;
createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (path === '/api/board') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    try { pending ??= getBoard().finally(() => { pending = null; }); res.end(JSON.stringify(await pending)); }
    catch (e) { res.statusCode = 502; res.end(JSON.stringify({ error: e.message })); }
    return;
  }
  const asset = assets[path];
  if (!asset) { res.writeHead(404).end('Bulunamadı'); return; }
  try { res.setHeader('Content-Type', asset[1] + '; charset=utf-8'); res.end(await readFile(fileURLToPath(new URL(asset[0], import.meta.url)))); }
  catch { res.writeHead(500).end('Dosya okunamadı'); }
}).listen(Number(process.env.PORT) || 3000, '127.0.0.1', () => console.log(`Okan Durak hazır: http://localhost:${Number(process.env.PORT) || 3000}`));
