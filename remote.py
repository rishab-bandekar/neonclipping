"""Hosted web UI: the NeonClipping page can be opened from a website (for example on Vercel) while every download,
speech model and render still runs here, on this PC and its GPU.

Every request passes one gate (middleware):

1. The Host header must be an IP address, localhost or a single-label name. A web page on attacker.example that
   re-points its DNS name at 127.0.0.1 (DNS rebinding) therefore gets nothing.
2. A request carrying an Origin header must come from this app's own page (same host) or from a website listed in
   NEONCLIPPING_UI_URL / DEFAULT_UI_URLS. Any other site gets 403, so a page you happen to visit cannot drive
   NeonClipping in the background.
3. Requests from the listed website also need the pairing token in the X-NeonClipping-Token header, except the CORS
   preflight and /remote/hello (which only says whether the browser is paired).
4. Requests without an Origin header (opening the page, <video>/<img> loads, local tools such as neon_mcp.py) work
   as before. Media ids are random, so a page that has not been paired cannot guess them.

Pairing: the token is kept in data/remote_token.txt. GET /open sends the browser to the website with the engine
address and token after the '#', which browsers never send to the website's server. /pair shows the same link and
the code on this PC, for pasting into another browser.
"""
import html
import hmac
import ipaddress
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

API = 1                                   # bump when the hosted page needs engine changes; the page checks it
HEADER = 'X-NeonClipping-Token'
DEFAULT_UI_URLS = ('https://neonclipping-chi.vercel.app',)   # the deployed website (tools/build_web.py + Vercel)
OPEN_PATHS = ('/remote/hello',)           # answered for the website before pairing
LOCAL_ONLY = ('/open', '/pair', '/remote/reset')   # hand out or change the token: never for a website


def ui_urls():
    """Websites allowed to use this engine, as origins (scheme://host[:port]). https only, except localhost for testing."""
    raw = os.environ.get('NEONCLIPPING_UI_URL')
    items = raw.split(',') if raw is not None else DEFAULT_UI_URLS
    out = []
    for item in items:
        p = urlsplit(item.strip())
        if not p.netloc or p.scheme not in ('https', 'http'):
            continue
        if p.scheme == 'http' and _host_name(p.netloc) not in ('localhost', '127.0.0.1', '::1'):
            continue                                   # a plain-http website could be impersonated on the network
        origin = f'{p.scheme}://{p.netloc}'.lower()
        if origin not in out:
            out.append(origin)
    return out


def _host_name(netloc):
    netloc = netloc.strip().lower()
    if netloc.startswith('['):
        return netloc[1:].split(']', 1)[0]
    return netloc.rsplit(':', 1)[0] if netloc.count(':') == 1 else netloc


def host_ok(host_header):
    """IP literals, localhost, *.localhost and single-label names (TestClient's 'testserver', a PC name).
    Any dotted name that is not an IP is refused: that is what a DNS-rebinding page would send."""
    name = _host_name(host_header or '')
    if not name or name == 'localhost' or name.endswith('.localhost') or '.' not in name and ':' not in name:
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def same_origin(origin, host_header):
    return urlsplit(origin).netloc.lower() == (host_header or '').strip().lower()


def _safe_name(name, fallback):
    name = re.sub(r'[^A-Za-z0-9._-]', '', str(name or ''))[:120].lstrip('.')
    return name or fallback


def attach(app, data):
    store = Path(data) / 'remote_token.txt'

    def token(renew=False):
        if not renew:
            try:
                got = store.read_text(encoding='utf-8').strip()
                if len(got) >= 32:
                    return got
            except OSError:
                pass
        new = secrets.token_urlsafe(32)
        store.parent.mkdir(parents=True, exist_ok=True)
        tmp = store.with_suffix('.tmp')
        tmp.write_text(new, encoding='utf-8')
        tmp.replace(store)
        return new

    def token_ok(got):
        return bool(got) and hmac.compare_digest(got.encode(), token().encode())

    def engine_address(request):
        port = request.url.port or int(os.environ.get('NEONCLIPPING_PORT', '8770'))
        return f'http://127.0.0.1:{port}'

    def pair_link(request):
        urls = ui_urls()
        if not urls:
            return None
        return urls[0] + '/#' + urlencode({'engine': engine_address(request), 'pair': token()})

    def download_headers(request, response):
        """?dl=1 on a file (clip, cover) makes the browser save it. A website cannot use <a download> for a file
        that lives on another address, so the hosted page asks for this instead."""
        if request.query_params.get('dl') == '1' and response.status_code == 200:
            name = _safe_name(request.query_params.get('name'), request.url.path.rstrip('/').rsplit('/', 1)[-1])
            response.headers['Content-Disposition'] = f'attachment; filename="{name}"'
        return response

    @app.middleware('http')
    async def remote_gate(request: Request, call_next):
        host = request.headers.get('host', '')
        if not host_ok(host):
            return JSONResponse({'detail': "NeonClipping only answers on this computer's own address."}, status_code=403)
        origin = request.headers.get('origin')
        path = request.url.path
        if origin is None or same_origin(origin, host):
            return download_headers(request, await call_next(request))
        allowed = origin.rstrip('/').lower()
        if allowed not in ui_urls() or path in LOCAL_ONLY:
            return JSONResponse({'detail': 'Blocked: this request came from another website.'}, status_code=403)
        cors = {'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Access-Control-Expose-Headers': 'Content-Disposition'}
        if request.method == 'OPTIONS':
            pre = {**cors, 'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
                   'Access-Control-Allow-Headers': f'Content-Type, {HEADER}', 'Access-Control-Max-Age': '600'}
            if request.headers.get('access-control-request-private-network') == 'true':
                pre['Access-Control-Allow-Private-Network'] = 'true'
            return Response(status_code=204, headers=pre)
        if path not in OPEN_PATHS and not token_ok(request.headers.get(HEADER, '')):
            return JSONResponse({'detail': 'Pair this browser with NeonClipping first.', 'pair': True},
                                status_code=401, headers=cors)
        response = download_headers(request, await call_next(request))
        response.headers.update(cors)
        return response

    @app.get('/remote/hello')
    def hello(request: Request):
        try:
            import updater
            version = updater.current(Path(__file__).resolve().parent)
        except Exception:      # noqa: BLE001 - the version is informational only
            version = ''
        return {'api': API, 'paired': token_ok(request.headers.get(HEADER, '')), 'version': version}

    @app.get('/open')
    def open_ui(request: Request):
        link = pair_link(request)
        return RedirectResponse(link or '/', status_code=302)

    @app.get('/pair')
    def pair_page(request: Request):
        link = pair_link(request)
        code = html.escape(token())
        if link:
            body = (f'<p>Open the NeonClipping website already connected to this PC:</p>'
                    f'<p><a class="btn" href="/open">Open {html.escape(ui_urls()[0])}</a></p>'
                    f'<p>Using another browser on this PC? Open the website there and paste this pairing code:</p>'
                    f'<p><code id="code">{code}</code> <button onclick="navigator.clipboard.writeText(document.getElementById(\'code\').textContent)">Copy</button></p>')
        else:
            body = '<p>No NeonClipping website is set up for this PC. Use <a href="/">the app on this PC</a>.</p>'
        body += ('<form method="post" action="/remote/reset"><p>Paired a browser you no longer trust? '
                 '<button>New code</button> (every paired browser must pair again)</p></form>')
        return HTMLResponse('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>Pair NeonClipping</title><style>body{font:16px system-ui;background:#0b0b12;color:#eee;'
                            'max-width:640px;margin:40px auto;padding:0 16px}a{color:#ff4fd8}code{word-break:break-all;'
                            'background:#1b1b26;padding:4px 6px;border-radius:6px}.btn{display:inline-block;padding:10px 16px;'
                            'background:#ff4fd8;color:#000;border-radius:10px;text-decoration:none;font-weight:600}</style>'
                            f'<h1>Pair a browser</h1>{body}')

    @app.post('/remote/reset')
    def reset():
        token(renew=True)
        return RedirectResponse('/pair', status_code=303)

    return token
