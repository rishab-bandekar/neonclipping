import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from captions_yt import pick_track


def track(code):
    return [{'ext': 'vtt', 'url': f'https://x/{code}.vtt'}, {'ext': 'json3', 'url': f'https://x/{code}.json3'}]


def info(language, auto=(), manual=()):
    return {'language': language,
            'automatic_captions': {k: track(k) for k in auto},
            'subtitles': {k: track(k) for k in manual}}


def picked(i, want=None):
    t = pick_track(i, want)
    return t and t['url'].rsplit('/', 1)[1].split('.')[0]


class PickTrack(unittest.TestCase):
    # An English stream the uploader marked Hindi: YouTube only made a Hindi speech track ('hi-orig');
    # 'en' in automatic_captions is a machine translation of it.
    MISLABELLED = info('hi', auto=('hi-orig', 'hi', 'en', 'fr'))

    def test_auto_keeps_the_declared_language_track(self):
        self.assertEqual(picked(self.MISLABELLED), 'hi-orig')
        self.assertEqual(picked(self.MISLABELLED, ''), 'hi-orig')

    def test_explicit_language_without_a_spoken_track_uses_the_speech_model(self):
        self.assertIsNone(picked(self.MISLABELLED, 'en'))       # never the translated 'en' track
        self.assertIsNone(picked(self.MISLABELLED, 'fr'))

    def test_hindi_and_hinglish_read_the_hindi_track(self):
        self.assertEqual(picked(self.MISLABELLED, 'hi'), 'hi-orig')
        self.assertEqual(picked(self.MISLABELLED, 'hinglish'), 'hi-orig')

    def test_explicit_language_matching_the_speech_track(self):
        i = info('en', auto=('en-orig', 'en', 'hi'))
        self.assertEqual(picked(i, 'en'), 'en-orig')
        self.assertIsNone(picked(i, 'hi'))                      # 'hi' here is a translation of English speech

    def test_declared_language_without_orig_suffix(self):
        self.assertEqual(picked(info('en', auto=('en',)), 'en'), 'en')

    def test_human_written_track_in_the_chosen_language(self):
        i = info('hi', auto=('hi-orig', 'en'), manual=('en',))
        self.assertIs(pick_track(i, 'en'), i['subtitles']['en'][1])     # the human track, not the auto translation

    def test_auto_falls_back_to_a_human_track_when_no_speech_track(self):
        self.assertEqual(picked(info('de', manual=('de',))), 'de')

    def test_no_tracks(self):
        self.assertIsNone(pick_track({}))
        self.assertIsNone(pick_track({}, 'en'))


if __name__ == '__main__':
    unittest.main()
