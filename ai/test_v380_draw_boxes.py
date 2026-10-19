#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path
import subprocess
import unittest
from v380_draw_boxes import inspect, draw_svg, draw_png

class Tests(unittest.TestCase):
    def test_png_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);jpg=p/'input.jpg';det=p/'input.json'
            source=Path('/mnt/usb2/V380/ai/parking.jpg')
            if source.is_file():
                import shutil
                shutil.copyfile(source,jpg)
            else:
                try:
                    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                        '-f','lavfi','-i','testsrc2=size=640x360:rate=1',
                        '-frames:v','1',str(jpg)],check=True,stdout=subprocess.DEVNULL)
                except (subprocess.CalledProcessError,FileNotFoundError):
                    self.skipTest('No 640x360 parking image and no FFmpeg lavfi')
            det.write_text(json.dumps({'width':640,'height':360,'objects':[
              {'label':'car','class_id':2,'confidence':.86,'bbox':[192,70,130,100]},
              {'label':'person','class_id':0,'confidence':.58,'bbox':[300,110,29,75]}]}))
            d=inspect(det)
            draw_svg(jpg,d,p/'output.svg')
            self.assertIn('CAR 86%',(p/'output.svg').read_text())
            self.assertIn('PERSON 58%',(p/'output.svg').read_text())
            self.assertIn('data:image/jpeg;base64,',(p/'output.svg').read_text())
            try:
                draw_png(jpg,d,p/'output.png')
            except RuntimeError:
                self.skipTest('SVG is supported; FFmpeg lacks RGB rawvideo output')
            self.assertTrue((p/'output.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            import struct
            self.assertEqual(struct.unpack('>II',(p/'output.png').read_bytes()[16:24]),(640,360))
    def test_bbox_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json';p.write_text(json.dumps({'width':640,'height':360,'objects':[{'label':'car','confidence':.9,'bbox':[1,2,3,float('inf')]}]}))
            with self.assertRaises(ValueError): inspect(p)
if __name__=='__main__': unittest.main()
