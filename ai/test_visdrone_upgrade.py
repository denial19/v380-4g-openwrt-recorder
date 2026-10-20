#!/usr/bin/env python3
"""Validate switcher safely against the *actual* installed V380 AI source."""
import unittest
from pathlib import Path
from v380_visdrone_switch import patched, MARKER, TARGET

class TestSwitcher(unittest.TestCase):
    @unittest.skipUnless(TARGET.exists(),'Run on V380 OpenWrt router with existing monitoring installed')
    def test_live_patching_without_writing(self):
        original=TARGET.read_text()
        if MARKER in original:
            self.skipTest('VisDrone already active')
        for sz in ('640','960'):
            new=patched(original,sz)
            compile(new,'v380_ai_alerts.py','exec')
            self.assertIn("objects = detect(jpeg, key)",new)
            self.assertIn("MODEL = AI / 'yolo11n'",new)
            self.assertIn(f"VISDRONE_MODEL = AI / 'visdrone/models/{sz}'",new)
            self.assertIn("'car', 'truck', 'bus', 'van'",new)
            self.assertEqual(original.count('def detect(jpeg):'),1)
            self.assertEqual(new.count('def detect(jpeg, view=None):'),1)
            self.assertEqual(original.count('def update_vehicle'),new.count('def update_vehicle'))
            self.assertEqual(original.count('def update_people'),new.count('def update_people'))
        print('PASS: read-only preview of both candidate patches against LIVE source')

if __name__=='__main__':unittest.main()
