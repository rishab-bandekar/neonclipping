"""Build the NeonClipping website for static hosting (Vercel or any static host).

The website shows the normal interface (index.html and its scripts and styles, copied from this repository).
web/connect.js points every request at the NeonClipping engine on the visitor's own computer
(http://127.0.0.1:8770), so downloads, speech models and rendering use that computer and its GPU.

    python tools/build_web.py                 # writes dist/web
    vercel deploy dist/web --prod             # publish it

After the first deploy, put the website address in remote.py (DEFAULT_UI_URLS) so installed engines accept it.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE = re.compile(r'<link rel="stylesheet" href="/assets/([^"]+)"\s*/?>')
SCRIPT = re.compile(r'<script src="/assets/([^"]+)"\s*>\s*</script>')
LOOPBACK = 'http://127.0.0.1:* http://localhost:*'
CSP = '; '.join((
    "default-src 'self'",
    "script-src 'self'",                                   # the interface has no inline scripts or eval
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    f"img-src 'self' data: blob: https: {LOOPBACK}",
    f"media-src 'self' blob: {LOOPBACK}",
    f"connect-src 'self' {LOOPBACK}",
    f"frame-src {LOOPBACK}",
    f"base-uri 'self' {LOOPBACK}",
    f"form-action 'self' {LOOPBACK}",
    "object-src 'none'",
))
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="color-scheme" content="dark">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<link rel="stylesheet" href="connect.css">
<script type="application/json" id="nc-site">{site}</script>
<script src="connect.js"></script>
</head>
<body>
<div id="nc-connect"></div>
<template id="nc-app">{body}</template>
</body>
</html>
"""
VERCEL = {
    '$schema': 'https://openapi.vercel.sh/vercel.json',
    'cleanUrls': True,
    'headers': [
        {'source': '/(.*)', 'headers': [
            {'key': 'Content-Security-Policy', 'value': "frame-ancestors 'none'"},
            {'key': 'X-Frame-Options', 'value': 'DENY'},
            {'key': 'X-Content-Type-Options', 'value': 'nosniff'},
            {'key': 'Referrer-Policy', 'value': 'no-referrer'},
        ]},
        {'source': '/NeonClipping-Setup.bat', 'headers': [
            {'key': 'Content-Disposition', 'value': 'attachment; filename="NeonClipping-Setup.bat"'},
        ]},
        {'source': '/install.sh', 'headers': [
            {'key': 'Content-Type', 'value': 'text/plain; charset=utf-8'},
        ]},
    ],
}


def api_version():
    m = re.search(r'^API = (\d+)', (ROOT / 'remote.py').read_text(encoding='utf-8'), re.M)
    return int(m.group(1))


def build(out):
    page = (ROOT / 'index.html').read_text(encoding='utf-8')
    head, rest = page.split('<body>', 1)
    body = rest.rsplit('</body>', 1)[0]
    css, js = STYLE.findall(head), SCRIPT.findall(body)
    if not css or not js:
        raise SystemExit('index.html changed: no /assets/ styles or scripts found')
    body = SCRIPT.sub('', body).strip()
    if '<script' in body or '</template' in body:
        raise SystemExit('index.html has an inline script or a </template>; update build_web.py')
    title = re.search(r'<title>(.*?)</title>', head, re.S).group(1)

    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():                        # start clean, but keep the Vercel project link (.vercel)
        if old.name != '.vercel':
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    (out / 'assets').mkdir()
    for name in css + js:
        shutil.copyfile(ROOT / name.split('?')[0], out / 'assets' / name.split('?')[0])
    site = json.dumps({'api': api_version(), 'css': ['assets/' + n for n in css], 'js': ['assets/' + n for n in js]})
    (out / 'index.html').write_text(PAGE.format(csp=CSP, title=title, site=site.replace('<', '\\u003c'), body=body),
                                    encoding='utf-8')
    for name in ('connect.js', 'connect.css'):
        shutil.copyfile(ROOT / 'web' / name, out / name)
    for name in ('NeonClipping-Setup.bat', 'install.sh'):
        shutil.copyfile(ROOT / name, out / name)
    (out / 'vercel.json').write_text(json.dumps(VERCEL, indent=2) + '\n', encoding='utf-8')
    # `vercel link` drops .env.local (a Vercel token) and .gitignore here: never publish them
    (out / '.vercelignore').write_text('.env*\n.gitignore\n', encoding='utf-8')
    return sorted(str(p.relative_to(out)).replace('\\', '/') for p in out.rglob('*') if p.is_file())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(ROOT / 'dist' / 'web'))
    files = build(Path(parser.parse_args().out))
    print('\n'.join(files))
