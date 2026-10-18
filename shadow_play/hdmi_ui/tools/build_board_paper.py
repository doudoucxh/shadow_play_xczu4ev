"""Regenerate deterministic board paper PNG caches (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw
import math,random
root=Path(__file__).resolve().parents[1]/'source';rng=random.Random(1018)
w,h=1000,550
im=Image.new('RGB',(w,h));px=im.load()
for y in range(h):
 for x in range(w):
  edge=min(x,w-1-x,y,h-1-y)
  shade=12*math.exp(-edge/20)+9*math.exp(-x/40)
  warm=3*math.sin(x/w*math.pi)
  grain=rng.random()*1.4+math.sin((y+x*.052)*2.1)*.7
  px[x,y]=tuple(round(c-shade+grain+warm) for c in (220,218,193))
d=ImageDraw.Draw(im)
for inset,color in [(3,'#cfc6a7'),(4,'#a79b78'),(13,'#b4a584'),(16,'#e3d7b9'),(17,'#b7a582')]:d.rectangle((inset,inset,w-inset-1,h-inset-1),outline=color)
im.save(root/'assets/board-paper.png',optimize=True)
w=h=256;im=Image.new('RGBA',(w,h));px=im.load()
for y in range(h):
 for x in range(w):
  edge=min(x,w-1-x,y,h-1-y)
  a=80*math.exp(-edge/5)+35*math.exp(-((x/w/.25)**2+(y/h/.22)**2))+42*math.exp(-(((1-x/w)/.27)**2+((1-y/h)/.24)**2))
  px[x,y]=(97,54,19,min(110,round(a)))
im.save(root/'assets/board-vignette.png',optimize=True)
