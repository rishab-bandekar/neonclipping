import json, re, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build_web


class BuildWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'web'
        cls.files = build_web.build(cls.out)
        cls.page = (cls.out / 'index.html').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_interface_file_is_published(self):
        site = json.loads(re.search(r'<script type="application/json" id="nc-site">(.*?)</script>', self.page, re.S).group(1))
        self.assertEqual(site['api'], build_web.api_version())
        for ref in site['css'] + site['js']:
            self.assertIn(ref.split('?')[0], self.files)
        for name in ('connect.js', 'connect.css', 'vercel.json', 'NeonClipping-Setup.bat', 'install.sh'):
            self.assertIn(name, self.files)

    def test_interface_markup_is_inert_until_the_engine_answers(self):
        template = self.page.split('<template id="nc-app">', 1)[1].split('</template>', 1)[0]
        self.assertIn('class="sidebar"', template)
        self.assertNotIn('<script', template)
        self.assertEqual(re.findall(r'<script src="([^"]+)"', self.page), ['connect.js'])   # nothing inline

    def test_security_headers(self):
        self.assertIn("script-src 'self'", self.page)
        self.assertIn('base-uri', self.page)
        headers = json.loads((self.out / 'vercel.json').read_text(encoding='utf-8'))['headers'][0]['headers']
        self.assertIn({'key': 'X-Frame-Options', 'value': 'DENY'}, headers)


if __name__ == '__main__':
    unittest.main()
