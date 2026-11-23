import os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
import remote

UI = 'https://clips.example.app'


def make_client():
    tmp = tempfile.TemporaryDirectory()
    app = FastAPI()

    @app.get('/library')
    def library():
        return {'items': []}

    @app.post('/make')
    def make(body: dict):
        return {'job': 'x'}

    @app.get('/media/{id}')
    def media(id: str):
        return PlainTextResponse('video')

    token = remote.attach(app, tmp.name)
    client = TestClient(app, base_url='http://127.0.0.1:8770')
    client.tmp = tmp
    return client, token


class RemoteGate(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'NEONCLIPPING_UI_URL': UI})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c, self.token = make_client()
        self.addCleanup(self.c.tmp.cleanup)

    def test_requests_without_origin_work_as_before(self):
        self.assertEqual(self.c.get('/library').status_code, 200)
        self.assertEqual(self.c.post('/make', json={}).status_code, 200)

    def test_the_apps_own_page_is_allowed(self):
        r = self.c.post('/make', json={}, headers={'Origin': 'http://127.0.0.1:8770'})
        self.assertEqual(r.status_code, 200)

    def test_other_websites_are_blocked(self):
        for origin in ('https://evil.example', 'null', 'http://127.0.0.1:9999'):
            self.assertEqual(self.c.post('/make', json={}, headers={'Origin': origin}).status_code, 403, origin)
            self.assertEqual(self.c.get('/library', headers={'Origin': origin}).status_code, 403, origin)

    def test_dns_rebinding_host_is_blocked(self):
        self.assertEqual(self.c.get('/library', headers={'Host': 'attacker.example:8770'}).status_code, 403)
        for host in ('127.0.0.1:8770', 'localhost:8770', '[::1]:8770', 'my-pc', '192.168.1.20:8770', 'app.localhost'):
            self.assertEqual(self.c.get('/library', headers={'Host': host}).status_code, 200, host)

    def test_website_needs_the_pairing_token(self):
        r = self.c.get('/library', headers={'Origin': UI})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers['access-control-allow-origin'], UI)      # the page can read why
        self.assertTrue(r.json()['pair'])
        r = self.c.get('/library', headers={'Origin': UI, remote.HEADER: 'wrong'})
        self.assertEqual(r.status_code, 401)
        r = self.c.post('/make', json={}, headers={'Origin': UI, remote.HEADER: self.token()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['access-control-allow-origin'], UI)

    def test_preflight(self):
        r = self.c.options('/make', headers={'Origin': UI, 'Access-Control-Request-Method': 'POST',
                                             'Access-Control-Request-Headers': 'content-type,x-neonclipping-token',
                                             'Access-Control-Request-Private-Network': 'true'})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers['access-control-allow-origin'], UI)
        self.assertIn(remote.HEADER, r.headers['access-control-allow-headers'])
        self.assertEqual(r.headers['access-control-allow-private-network'], 'true')

    def test_hello_reports_pairing_without_a_token(self):
        self.assertEqual(self.c.get('/remote/hello', headers={'Origin': UI}).json()['paired'], False)
        j = self.c.get('/remote/hello', headers={'Origin': UI, remote.HEADER: self.token()}).json()
        self.assertEqual((j['paired'], j['api']), (True, remote.API))

    def test_token_pages_are_never_served_to_a_website(self):
        for path in ('/open', '/pair'):
            self.assertEqual(self.c.get(path, headers={'Origin': UI, remote.HEADER: self.token()}).status_code, 403, path)
        self.assertEqual(self.c.post('/remote/reset', headers={'Origin': UI, remote.HEADER: self.token()}).status_code, 403)

    def test_open_sends_the_token_after_the_hash(self):
        r = self.c.get('/open', follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers['location'], f'{UI}/#engine=http%3A%2F%2F127.0.0.1%3A8770&pair={self.token()}')

    def test_reset_makes_a_new_token_that_persists(self):
        old = self.token()
        self.assertEqual(self.c.post('/remote/reset', headers={'Origin': 'http://127.0.0.1:8770'}, follow_redirects=False).status_code, 303)
        new = self.token()
        self.assertNotEqual(old, new)
        self.assertEqual(self.token(), new)
        self.assertEqual(self.c.get('/library', headers={'Origin': UI, remote.HEADER: old}).status_code, 401)

    def test_download_header(self):
        r = self.c.get('/media/abc123?dl=1&name=neonclipping-abc.mp4', headers={'Origin': UI, remote.HEADER: self.token()})
        self.assertEqual(r.headers['content-disposition'], 'attachment; filename="neonclipping-abc.mp4"')
        r = self.c.get('/media/abc123?dl=1&name=../../x"y.mp4')
        self.assertEqual(r.headers['content-disposition'], 'attachment; filename="xy.mp4"')
        self.assertNotIn('content-disposition', self.c.get('/media/abc123').headers)


class Settings(unittest.TestCase):
    def test_ui_urls(self):
        with mock.patch.dict(os.environ, {'NEONCLIPPING_UI_URL': 'https://A.example/, http://evil.example, http://localhost:5500,ftp://x'}):
            self.assertEqual(remote.ui_urls(), ['https://a.example', 'http://localhost:5500'])
        with mock.patch.dict(os.environ, {'NEONCLIPPING_UI_URL': ''}):
            self.assertEqual(remote.ui_urls(), [])

    def test_open_without_a_website_goes_to_the_local_app(self):
        with mock.patch.dict(os.environ, {'NEONCLIPPING_UI_URL': ''}):
            c, _ = make_client()
            self.addCleanup(c.tmp.cleanup)
            self.assertEqual(c.get('/open', follow_redirects=False).headers['location'], '/')


if __name__ == '__main__':
    unittest.main()
