import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('parking_events', Path(__file__).with_name('parking_events.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def frame(items):
    return {'width': 640, 'height': 360,
            'objects': [{'label': 'car', 'confidence': .95, 'bbox': b} for b in items]}


class EventTests(unittest.TestCase):
    def test_one_of_two_departs(self):
        s = {}
        a = [120, 70, 90, 60]
        b = [340, 90, 100, 55]
        for seq, f in enumerate([frame([a,b]), frame([a,b]),frame([a]),frame([a])]):
            s, e = module.update(s, f, str(seq))
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]['event'], 'vehicle_no_longer_detected')
        self.assertEqual(len([x for x in s['tracks'] if x['misses']==0]), 1)

    def test_no_repeated_alert_for_same_file(self):
        s = {}
        box=[120,70,90,60]
        for seq, f in enumerate([frame([box]),frame([box]),frame([]),frame([])]):
            s, e = module.update(s, f, str(seq))
        self.assertEqual(len(e), 1)
        s, e = module.update(s, frame([]), '3')
        self.assertEqual(e, [])
        s, e = module.update(s, frame([]), '4')
        self.assertEqual(e, [])

    def test_unconfirmed_false_detection(self):
        s = {}
        box=[120,70,90,60]
        for seq, f in enumerate([frame([box]),frame([]),frame([])]):
            s, e = module.update(s, f, str(seq))
        self.assertEqual(e, [])

    def test_invalid_frame_not_absence(self):
        s={}
        with self.assertRaises(ValueError):
            module.update(s, {'width':640,'height':360}, 'bad')

if __name__ == '__main__':
    unittest.main()
