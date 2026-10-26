"""Okan ulaşım: dependency-free IETT SOAP gateway and web application."""
import concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json, os, re, threading, time
import urllib.request
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
LINES = json.loads((ROOT / 'data/lines.json').read_text())
TZ = ZoneInfo('Europe/Istanbul')
CACHE = {}
LOCK = threading.Lock()

def soap(path, operation, args=None):
    fields = ''.join(f'<{k}>{escape(str(v))}</{k}>' for k,v in (args or {}).items())
    body = f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><{operation} xmlns="http://tempuri.org/">{fields}</{operation}></soap:Body></soap:Envelope>'
    request = urllib.request.Request('https://api.ibb.gov.tr/iett/'+path+'.asmx', data=body.encode(), headers={'Content-Type':'text/xml; charset=utf-8','SOAPAction':f'"http://tempuri.org/{operation}"'})
    with urllib.request.urlopen(request, timeout=22) as response:
        root = ET.fromstring(response.read())
    result = next((e.text for e in root.iter() if e.tag.endswith(operation+'Result')), None)
    if result is None: raise ValueError('İETT boş veya beklenmeyen yanıt döndürdü.')
    data = json.loads(result)
    if not isinstance(data, list): raise ValueError('İETT veri biçimi değişti.')
    return data

def cached(key, load, ttl):
    with LOCK: old = CACHE.get(key)
    if old and time.time()-old[0] < ttl:
        return {'data':old[1], 'updatedAt':old[2], 'stale':False, 'error':None}
    try:
        data = load(); stamp = datetime.now(TZ).isoformat()
        with LOCK: CACHE[key] = (time.time(),data,stamp)
        return {'data':data,'updatedAt':stamp,'stale':False,'error':None}
    except Exception:
        return {'data':old[1] if old else [], 'updatedAt':old[2] if old else None, 'stale':bool(old), 'error':'İETT servisine ulaşılamadı. Tekrar deneyin.'}

def announcements():
    return cached('notices',lambda:soap('UlasimDinamikVeri/Duyurular','GetDuyurular_json'),60)

def schedules(line):
    return cached(line['code'],lambda:soap('UlasimAnaVeri/PlanlananSeferSaati','GetPlanlananSeferSaati_json',{'HatKodu':line['code']}),300)

def minutes(value):
    if not re.fullmatch(r'\d{1,2}:\d{2}', value or ''): return None
    h,m = map(int,value.split(':'))
    return h*60+m if 0 <= h <= 47 and 0 <= m < 60 else None

def normalize(line, rows):
    # Only GTFS variants proven to visit Okan, or the verified KM28 base route.
    allowed=set(line['routeCodes'])
    if not allowed: allowed={f"{line['code']}_{d}_D0" for d in line['directions']}
    seen=set(); result=[]
    for row in rows:
        route=row.get('SGUZERAH',''); t=row.get('DT',''); direction=row.get('SYON'); day=row.get('SGUNTIPI')
        if route not in allowed or minutes(t) is None or direction not in ('D','G') or day not in ('I','C','P'): continue
        key=(t,direction,day,route)
        if key in seen: continue
        seen.add(key)
        result.append({'time':t,'minutes':minutes(t),'direction':direction,'day':day,'route':route,'marker':row.get('GUZERGAH_ISARETI') or ''})
    return sorted(result,key=lambda x:(x['day'],x['direction'],x['minutes']))

def dashboard():
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        nf=pool.submit(announcements)
        futures=[pool.submit(schedules,line) for line in LINES]
        results=[f.result() for f in futures]; notices=nf.result()
    lines=[]
    for line,result in zip(LINES,results):
        items=[{'type':n.get('TIP',''),'message':n.get('MESAJ',''),'recordedAt':n.get('GUNCELLEME_SAATI','')} for n in notices['data'] if str(n.get('HATKODU','')).strip().upper()==line['code']]
        lines.append({**line,'schedule':normalize(line,result['data']),'scheduleState':{k:v for k,v in result.items() if k!='data'},'notices':items})
    return {'lines':lines,'noticesState':{k:v for k,v in notices.items() if k!='data'},'now':datetime.now(TZ).isoformat(),'timezone':'Europe/Istanbul'}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'public'),**kwargs)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/dashboard':
            try:
                body=json.dumps(dashboard(),ensure_ascii=False).encode();self.send_response(200)
            except Exception:
                body=json.dumps({'error':'Veriler hazırlanamadı.'}).encode();self.send_response(500)
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        elif path=='/health':
            self.send_response(200);self.end_headers();self.wfile.write(b'ok')
        else: super().do_GET()

if __name__=='__main__':
    port=int(os.environ.get('PORT','3000'))
    print(f'Okan ulaşım listening on port {port}',flush=True)
    ThreadingHTTPServer((os.environ.get('HOST','0.0.0.0'),port),Handler).serve_forever()
