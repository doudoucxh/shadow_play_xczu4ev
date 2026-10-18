import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]/'hdmi_ui/runtime'))
from virtual_screen import xwd_layout, X11Pointer

class VirtualScreenTests(unittest.TestCase):
    def test_native_input_keeps_strokes_and_release_order(self):
        calls=[]
        class Native:
            def XTestFakeMotionEvent(self,*args):calls.append(('move',args[2],args[3]))
            def XTestFakeButtonEvent(self,*args):calls.append(('button',args[2]))
            def XFlush(self,*args):calls.append(('flush',))
            def XCloseDisplay(self,*args):calls.append(('close',))
        pointer=X11Pointer.__new__(X11Pointer)
        pointer.x=pointer.t=Native();pointer.handle=1
        pointer.send([('down',[20,30]),('move',[21,31]),('move',[22,32]),('up',[23,33])])
        self.assertEqual(calls,[('move',20,30),('button',1),('move',21,31),('move',22,32),('move',23,33),('button',0),('flush',)])
        with self.assertRaises(ValueError):pointer.send([('move',[-1,0])])
        pointer.close()
        self.assertEqual(calls[-3:],[('button',0),('flush',),('close',)])

    def header(self):
        return [116,7,2,24,1024,600,0,0,32,0,32,32,4096,4,0xff0000,0xff00,0xff,8,256,256,1024,600,0,0,0]

    def test_known_pixel_layout_and_bounds(self):
        header=self.header()
        size=116+256*12+1024*600*4
        self.assertEqual(xwd_layout(struct.pack('!25I',*header),size),(3188,1024,600))
        for index,value in [(0,99),(1,6),(4,2048),(7,1),(11,24),(12,8192),(14,0xff),(19,257)]:
            bad=header.copy();bad[index]=value
            with self.assertRaises(ValueError):xwd_layout(struct.pack('!25I',*bad),size)
        with self.assertRaises(ValueError):xwd_layout(struct.pack('!25I',*header),size-1)

if __name__=='__main__':unittest.main()
