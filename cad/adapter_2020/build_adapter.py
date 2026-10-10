"""SGX-2020 adapter: dimensioned DXF/PDF, 1:1 DXF and optional STEP.

All positions and dimensions are in mm. This is a fit-check design, not a
certification of the slide's allowable overturning moment or dynamic payload.
"""
from pathlib import Path
import sys, math, json, zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tmp' / 'cad_deps'))
sys.path.insert(0, str(ROOT / 'tmp' / 'ocp_deps'))
OUT = Path(__file__).resolve().parent
PDF_DIR = ROOT / 'output' / 'pdf'
PDF_DIR.mkdir(parents=True, exist_ok=True)
import ezdxf
from ezdxf.enums import TextEntityAlignment
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

NAME = 'SGX_2020_adapter_60x60x8_R0'
P = dict(width=60., length=60., thickness=8., corner_radius=2.,
         mounting_pitch=30., clearance_diameter=4.5,
         counterbore_diameter=8., counterbore_depth=4.5,
         bracket_pitch=40., bracket_thread='M5x0.8-6H', tap_drill=4.2)
A = [(-15.,-15.), (15.,-15.), (15.,15.), (-15.,15.)]
B = [(0.,20.), (20.,0.), (0.,-20.), (-20.,0.)]
COLORS = {'OUTLINE':(0.08,0.11,0.15), 'HOLES':(0.08,0.11,0.15),
          'COUNTERBORE':(0.08,0.11,0.15), 'THREAD':(0.1,0.1,0.1),
          'DIM':(0.12,0.16,0.21), 'TEXT':(0.09,0.12,0.16),
          'CENTER':(0.38,0.43,0.49), 'REF':(0.15,0.43,0.59),
          'HIDDEN':(0.4,0.43,0.46), 'HATCH':(0.5,0.53,0.55)}
ACI = {'OUTLINE':7,'HOLES':7,'COUNTERBORE':7,'THREAD':7,'DIM':7,
       'TEXT':7,'CENTER':8,'REF':4,'HIDDEN':8,'HATCH':8}

def doc_new():
    d = ezdxf.new('R2010', setup=True)
    d.units = 4
    d.header['$MEASUREMENT'] = 1
    d.header['$LUNITS'] = 2
    d.header['$LUPREC'] = 3
    d.header['$INSBASE'] = (0.,0.,0.)
    d.styles.new('CN', dxfattribs={'font':'simhei.ttf'})
    for name,col in ACI.items():
        d.layers.new(name, dxfattribs={'color':col,'lineweight':35 if name=='OUTLINE' else 18,
                                     'linetype':'DASHED' if name in ('REF','HIDDEN') else 'CONTINUOUS'})
    return d

pdfmetrics.registerFont(TTFont('CN', 'C:/Windows/Fonts/simhei.ttf'))

class Sheet:
    def __init__(self, doc, pdf, dxf_offset=0):
        self.d = doc
        self.m = doc.modelspace()
        self.c = pdf
        self.dx = dxf_offset
    def style(self, layer, w=.22):
        self.c.setStrokeColorRGB(*COLORS[layer])
        self.c.setFillColorRGB(*COLORS[layer])
        self.c.setLineWidth(w*mm)
        self.c.setDash([2*mm,1.2*mm] if layer in ('REF','HIDDEN','CENTER') else [])
    def line(self,x1,y1,x2,y2,layer='OUTLINE',w=.22):
        self.m.add_line((x1+self.dx,y1),(x2+self.dx,y2),dxfattribs={'layer':layer})
        self.style(layer,w); self.c.line(x1*mm,y1*mm,x2*mm,y2*mm)
    def poly(self,pts,layer='OUTLINE',close=False,fill=False,w=.22):
        self.m.add_lwpolyline([(x+self.dx,y) for x,y in pts],close=close,dxfattribs={'layer':layer})
        self.style(layer,w)
        p=self.c.beginPath();p.moveTo(pts[0][0]*mm,pts[0][1]*mm)
        for x,y in pts[1:]:p.lineTo(x*mm,y*mm)
        if close:p.close()
        self.c.drawPath(p,fill=int(fill),stroke=1)
    def rect(self,x,y,w,h,layer='OUTLINE',fill=False):
        self.poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],layer,True,fill)
    def circle(self,x,y,r,layer='HOLES',w=.22):
        self.m.add_circle((x+self.dx,y),r,dxfattribs={'layer':layer})
        self.style(layer,w);self.c.circle(x*mm,y*mm,r*mm,stroke=1,fill=0)
    def arc(self,x,y,r,start,end,layer='OUTLINE',w=.22):
        self.m.add_arc((x+self.dx,y),r,start,end,dxfattribs={'layer':layer})
        self.style(layer,w);self.c.arc((x-r)*mm,(y-r)*mm,(x+r)*mm,(y+r)*mm,start,end-start)
    def text(self,x,y,t,h=3.2,layer='TEXT',align='left',rot=0):
        # SimHei includes Greek phi but not Latin O-stroke or typographic bullets.
        t=t.replace('Ø','φ').replace('•','-')
        e=self.m.add_text(t,dxfattribs={'height':h,'style':'CN','layer':layer,'rotation':rot})
        e.set_placement((x+self.dx,y),align={'left':TextEntityAlignment.LEFT,
                                          'center':TextEntityAlignment.CENTER,
                                          'right':TextEntityAlignment.RIGHT}[align])
        self.style(layer)
        self.c.saveState();self.c.translate(x*mm,y*mm);self.c.rotate(rot)
        self.c.setFont('CN',h*mm)
        {'left':self.c.drawString,'center':self.c.drawCentredString,'right':self.c.drawRightString}[align](0,0,t)
        self.c.restoreState()
    def arrow(self,x,y,angle,layer='DIM',size=2):
        a=math.radians(angle);u=(math.cos(a),math.sin(a));v=(-u[1],u[0])
        self.poly([(x,y),(x+size*u[0]+.32*size*v[0],y+size*u[1]+.32*size*v[1]),
                   (x+size*u[0]-.32*size*v[0],y+size*u[1]-.32*size*v[1])],layer,True,True,.12)
    def dimh(self,x1,x2,feature_y,dim_y,label):
        sign=1 if dim_y>feature_y else -1
        for x in (x1,x2):self.line(x,feature_y+sign*1,x,dim_y+sign*2,'DIM',.13)
        self.line(x1,dim_y,x2,dim_y,'DIM',.13)
        self.arrow(x1,dim_y,0);self.arrow(x2,dim_y,180)
        self.text((x1+x2)/2,dim_y+1.5,label,3.2,align='center')
    def dimv(self,y1,y2,feature_x,dim_x,label):
        sign=1 if dim_x>feature_x else -1
        for y in (y1,y2):self.line(feature_x+sign,y,dim_x+2*sign,y,'DIM',.13)
        self.line(dim_x,y1,dim_x,y2,'DIM',.13)
        self.arrow(dim_x,y1,90);self.arrow(dim_x,y2,270)
        self.text(dim_x-1.5,(y1+y2)/2,label,3.2,align='center',rot=90)

def frame(s,num,title):
    s.rect(8,8,404,281)
    s.text(16,278,title,6)
    s.text(16,270,'SGX 滑块 / 2020 立柱连接 | 所有尺寸单位：mm',3.4)
    s.text(404,279,'R0 · 实物配合待核对',4,align='right',layer='REF')
    s.text(404,271,'2026-09-26',3.2,align='right')
    s.line(8,265,412,265)
    s.rect(8,8,404,22)
    for x in (190,270,324,370):s.line(x,8,x,30)
    s.text(13,21,'零件：滑块-2020 立柱紧凑转接板',4)
    s.text(13,13,NAME,3.3)
    s.text(196,21,'材料：6061-T6 铝合金',3.4)
    s.text(196,13,'尺寸：60 × 60 × 8',3.4)
    s.text(276,21,'版本：R0',3.4)
    s.text(276,13,'状态：试配设计',3.4)
    s.text(330,21,'图幅：A3',3.4)
    s.text(330,13,'单位：mm',3.4)
    s.text(376,21,f'页：{num}/2',3.4)
    s.text(376,13,'数量：1',3.4)

def round_outline(s,cx,cy,k):
    lo=-30;hi=30;r=2
    cv=lambda x,y:(cx+x*k,cy+y*k)
    for a,b in [((-28,-30),(28,-30)),((30,-28),(30,28)),((28,30),(-28,30)),((-30,28),(-30,-28))]:
        s.line(*cv(*a),*cv(*b),w=.35)
    for x,y,a in [(28,28,0),(-28,28,90),(-28,-28,180),(28,-28,270)]:s.arc(*cv(x,y),r*k,a,a+90,w=.35)

def top_view(s):
    cx,cy,k=94,187,2
    cv=lambda x,y:(cx+x*k,cy+y*k)
    round_outline(s,cx,cy,k)
    s.line(*cv(-34,0),*cv(34,0),'CENTER',.13)
    s.line(*cv(0,-34),*cv(0,34),'CENTER',.13)
    for i,(x,y) in enumerate(A,1):
        s.circle(*cv(x,y),2.25*k);s.circle(*cv(x,y),4*k,'COUNTERBORE')
        s.line(*cv(x-5,y),*cv(x+5,y),'CENTER',.12)
        s.line(*cv(x,y-5),*cv(x,y+5),'CENTER',.12)
        s.text(*cv(x+(5 if x>0 else -5),y+4.5),f'A{i}',3,align='left' if x>0 else 'right')
    for i,(x,y) in enumerate(B,1):
        s.circle(*cv(x,y),2.1*k,'THREAD')
        s.arc(*cv(x,y),2.5*k,35,305,'THREAD',.12)
        s.text(*cv(x+3.5,y+3.5),f'B{i}',3)
    s.rect(*cv(-10,-10),20*k,20*k,'REF')
    s.text(cx,cy+2,'2020',3.8,'REF','center')
    s.text(cx,cy-4,'安装轮廓',3,'REF','center')
    s.text(cx+2,cy-10,'O',3,'CENTER')
    s.dimh(*[cv(-30,0)[0],cv(30,0)[0]],247,258,'60 ±0.10')
    s.dimv(127,247,34,20,'60 ±0.10')
    # Hole pitch below drawing, with extensions originating at the lower row.
    s.dimh(cv(-15,0)[0],cv(15,0)[0],157,116,'30 ±0.05')
    s.dimv(157,217,124,170,'30 ±0.05')
    s.text(cx,104,'俯视图（上表面） 2:1',3.8,align='center')
    s.text(cx,97,'蓝色虚线仅供装配参考，不加工。',3.1,'REF','center')
    # Section line B-B through the upper pair of slide holes.
    s.line(29,217,159,217,'CENTER',.15)
    s.arrow(29,217,90);s.arrow(159,217,90)
    s.text(26,221,'B',3.5);s.text(160,221,'B',3.5)
    s.poly([cv(28.6,29.4),(151,250),(167,250)],'DIM')
    s.text(158,252,'4-R2',3.2)

def section(s):
    cx,zbase,k=94,63,2
    cv=lambda x,z:(cx+x*k,zbase+z*k)
    # Two counterbores in this section, y=+15 mm.
    ranges=[(-30,-19),(-11,11),(19,30)]
    # Draw each connected section region without artificial material seams.
    regions=[
        [(-30,0),(-17.25,0),(-17.25,3.5),(-19,3.5),(-19,8),(-30,8)],
        [(-12.75,0),(12.75,0),(12.75,3.5),(11,3.5),(11,8),
         (-11,8),(-11,3.5),(-12.75,3.5)],
        [(17.25,0),(30,0),(30,8),(19,8),(19,3.5),(17.25,3.5)],
    ]
    for poly in regions:s.poly([cv(*p) for p in poly],close=True)
    for x in (-15,15):s.line(*cv(x,-2),*cv(x,10),'CENTER',.13)
    # Hatch continuous material regions, clipped in PDF and individually bounded in DXF.
    for a,b in ranges:
        for t in range(int((a-8)*2),int(b*2),3):
            q=t/2; lo=max(0,a-q);hi=min(8,b-q)
            if hi>lo:s.line(*cv(q+lo,lo),*cv(q+hi,hi),'HATCH',.1)
    for x in (-15,15):
        for a,b in [(x-4,x-2.25),(x+2.25,x+4)]:
            for q in [a-3,a-1.5,a,a+1.5]:
                lo=max(0,a-q);hi=min(3.5,b-q)
                if hi>lo:s.line(*cv(q+lo,lo),*cv(q+hi,hi),'HATCH',.1)
    s.dimv(63,79,154,170,'8 ±0.10')
    s.text(94,87,'B-B 剖视图 2:1',3.8,align='center')
    s.text(94,53,'上面沉孔深 4.5；剩余底厚 3.5',3.2,align='center')
    s.text(94,46,'M4 螺钉头沉入板内，下面保持平整。',3.1,align='center')

def hole_table(s):
    s.text(192,252,'孔加工表 / 坐标原点 O 为板中心',4.3)
    s.text(192,244,'+X 向右，+Y 向上；底面 Z=0，上面 Z=8。',3.3)
    x,y,w,row=192,237,210,7.5
    columns=[0,25,49,73,210]
    rows=[['编号','X','Y','加工要求'],
          ['A1','-15','-15','Ø4.5 通孔；上面 Ø8 沉孔，深 4.5'],
          ['A2','15','-15','同 A1'],['A3','15','15','同 A1'],['A4','-15','15','同 A1'],
          ['B1','0','20','M5×0.8-6H 通螺纹；底孔 Ø4.2'],
          ['B2','20','0','同 B1'],['B3','0','-20','同 B1'],['B4','-20','0','同 B1']]
    for i,r in enumerate(rows):
        yy=y-i*row
        s.line(x,yy,x+w,yy,'DIM',.15)
        for j,t in enumerate(r):s.text(x+columns[j]+2,yy-5.1,t,3.15)
    s.line(x,y-len(rows)*row,x+w,y-len(rows)*row,'DIM',.15)
    for q in columns:s.line(x+q,y,x+q,y-len(rows)*row,'DIM',.15)
    s.text(192,159,'加工要求',4.2)
    notes=[
      '1. 外形 60×60；厚 8；四个外圆角 R2。',
      '2. A 孔：Ø4.5 +0.15/0；Ø8 沉孔 +0.20/0，深 4.5 +0.20/0。',
      '3. 孔中心坐标公差 ±0.05；外形和厚度公差见图。',
      '4. 上、下面平面度各 0.10；上下表面平行度 0.10。',
      '5. 去毛刺；未注锐边轻倒钝 0.2～0.3；装配面不得留凸起。',
      '6. B 孔螺纹为正式加工要求，STEP 用 Ø4.2 底孔简化表示。',
      '7. 蓝色轮廓和中心线为参考线，不能作为切割轮廓。',
    ]
    for i,t in enumerate(notes):s.text(192,150-i*7,t,3.2)
    s.text(192,91,'配合条件：加工前核对实物',4.1,'REF')
    for i,t in enumerate([
      '滑块外侧四孔必须为 M4，中心距 30×30，且孔深足够。',
      '内侧四个沉孔不用于本转接板安装；核对其螺钉头不凸出。',
      '立柱选 2020；角码底孔中心距型材贴合面应为 10 mm。',
      '负载、加速度和滑台允许倾覆力矩未定，本图不标额定载荷。',
      '现有依据：厂家 SGX 图纸；实物型号与螺纹尚未确认。',
    ]):s.text(192,82-i*7,t,3.2,'REF')

def assembly(s):
    frame(s,2,'安装说明与配合检查')
    s.text(20,250,'装配示意（非加工视图；型材长度局部缩短）',4.2)
    # Simple side view, along Y. Nominal base, carriage, profile and L braces.
    cx,by,k=92,139,2
    s.rect(cx-60,by,120,16)
    s.rect(cx-60,by-36,120,36,'REF')
    s.text(cx,by-21,'滑块 60×42（参考）',3.3,'REF','center')
    s.rect(cx-20,by+16,40,83,'REF')
    s.line(cx-5,by+20,cx-5,by+95,'REF');s.line(cx+5,by+20,cx+5,by+95,'REF')
    s.text(cx,by+106,'2020 立柱，约 200 高',3.6,'REF','center')
    for sign in (-1,1):
        # Depict one 20x20 angle on either side, t=3; section of slots omitted.
        if sign==1:pts=[(112,155),(152,155),(152,161),(118,161),(118,195),(112,195)]
        else:pts=[(72,155),(32,155),(32,161),(66,161),(66,195),(72,195)]
        s.poly(pts,'REF',True)
        sx=cx+sign*40
        s.line(sx,145,sx,166,'CENTER')
        s.rect(sx-4.5,161,9,4,'REF')
        s.circle(cx+sign*24,175,3.5,'REF')
    s.text(92,92,'四面各一只角码；侧视仅显示两只。',3.3,align='center')
    s.text(20,74,'选角码的关键尺寸',4.1)
    for i,t in enumerate([
      '• 配 2020 型材；平底、无突出定位齿；建议金属角码。',
      '• 底孔中心距型材贴合面 10 mm，适配 M5 螺钉。',
      '• 从型材面向外伸出不超过 20 mm，宽不超过 20 mm。',
      '• 角码若有长孔，长孔范围须覆盖本板的固定孔位。',
    ]):s.text(20,66-i*7,t,3.2)
    s.text(190,249,'装配顺序',4.5)
    lines=[
      '1 先用四颗 M4 内六角圆柱头螺钉，将板固定在滑块上。',
      '   螺钉头放在上面沉孔内；板下面不放螺母。',
      '2 将 2020 立柱居中放置，使四面距板边均为 20 mm。',
      '3 四只角码底部用 M5 螺钉固定到 B1～B4 螺纹孔。',
      '   角码竖直面用 M5 螺钉和匹配槽型的 T 型螺母连接型材。',
      '4 校正立柱垂直度后交替紧固；再装上层托架和执行器。',
      '5 先以低速、低加速度验证往复和转动时的间隙及晃动。',
    ]
    for i,t in enumerate(lines):s.text(190,239-i*8,t,3.3)
    s.text(190,175,'螺钉长度：按实际孔深选择',4.2)
    for i,t in enumerate([
      'A 孔沉孔底到滑块顶面的距离为 3.5 mm。',
      'M4 螺钉进入滑块的长度 = 螺钉公称长度 L - 3.5。',
      '例如 M4×10 会进入约 6.5 mm；仅在有效孔深允许时使用。',
      '留出孔底余量，并核对滑块内机构位置，避免顶到底。',
      'B 孔 M5 螺钉：板内有效啮合建议 6～7 mm，端部不得凸出。',
      '角码厚度若为 3 mm，M5×10 可作为试配长度（不加垫片）。',
      '连接型材侧槽的螺钉长度按角码、T 型螺母和槽深另选。',
    ]):s.text(190,165-i*7,t,3.2)
    s.text(190,104,'交付文件与使用方法',4.2)
    for i,t in enumerate([
      'plate_1to1.dxf：毫米、1:1，板中心为原点；图层区分孔型。',
      'drawing.dxf：含两张 A3 图纸；模型空间中并排摆放。',
      'PDF：打印、询价和尺寸核对使用；不要从截图量尺寸。',
      'STEP：毫米实体；螺纹不建牙型，按加工表攻丝。',
      '本版仅适配 2020；3030/2040 或其他滑块需重新排孔。',
    ]):s.text(190,94-i*7,t,3.2)
    s.text(190,48,'预计板重约 73 g；不含螺钉、角码和立柱。',3.3,'REF')

def geometry_dxf():
    d=doc_new();m=d.modelspace()
    b=math.tan(math.pi/8)
    points=[(-28,-30,0),(28,-30,b),(30,-28,0),(30,28,b),
            (28,30,0),(-28,30,b),(-30,28,0),(-30,-28,b)]
    m.add_lwpolyline(points,format='xyb',close=True,dxfattribs={'layer':'OUTLINE'})
    for x,y in A:
        m.add_circle((x,y),2.25,dxfattribs={'layer':'HOLES'})
        m.add_circle((x,y),4.,dxfattribs={'layer':'COUNTERBORE'})
    for x,y in B:m.add_circle((x,y),2.1,dxfattribs={'layer':'THREAD'})
    d.set_modelspace_vport(75,center=(0,0))
    path=OUT/(NAME+'_plate_1to1.dxf');d.saveas(path)
    return path

def make_step():
    try:
        from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Fuse
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.STEPControl import STEPControl_Writer,STEPControl_Reader,STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
    except ImportError:
        return {'available':False}
    def cylinder(x,y,z,r,h):return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(0,0,1)),r,h).Shape()
    body=BRepPrimAPI_MakeBox(gp_Pnt(-28,-30,0),56,60,8).Shape()
    mid=BRepPrimAPI_MakeBox(gp_Pnt(-30,-28,0),60,56,8).Shape()
    body=BRepAlgoAPI_Fuse(body,mid).Shape()
    for x in (-28,28):
        for y in (-28,28):body=BRepAlgoAPI_Fuse(body,cylinder(x,y,0,2,8)).Shape()
    for x,y in A:
        body=BRepAlgoAPI_Cut(body,cylinder(x,y,-1,2.25,10)).Shape()
        body=BRepAlgoAPI_Cut(body,cylinder(x,y,3.5,4,5.5)).Shape()
    for x,y in B:body=BRepAlgoAPI_Cut(body,cylinder(x,y,-1,2.1,10)).Shape()
    assert BRepCheck_Analyzer(body).IsValid(), 'Invalid BREP before export'
    Interface_Static.SetCVal_s('write.step.schema','AP214IS')
    Interface_Static.SetCVal_s('write.step.unit','MM')
    writer=STEPControl_Writer();writer.Transfer(body,STEPControl_AsIs)
    path=OUT/(NAME+'.step')
    # OCCT's narrow Windows path APIs can mishandle Chinese directory names.
    import os
    prev=os.getcwd();os.chdir(OUT)
    try:
        assert writer.Write(path.name)==IFSelect_RetDone
        reader=STEPControl_Reader();assert reader.ReadFile(path.name)==IFSelect_RetDone
        reader.TransferRoots();readback=reader.OneShape()
    finally:os.chdir(prev)
    assert BRepCheck_Analyzer(readback).IsValid(), 'Invalid STEP readback'
    g=GProp_GProps();BRepGProp.VolumeProperties_s(readback,g)
    box=Bnd_Box();BRepBndLib.Add_s(readback,box)
    bb=box.Get(); extents=[bb[i+3]-bb[i] for i in range(3)]
    assert all(abs(a-b)<1e-5 for a,b in zip(extents,[60,60,8])),extents
    expected=(60*60-(4-math.pi)*2**2)*8-4*math.pi*(2.25**2*8+(4**2-2.25**2)*4.5)-4*math.pi*2.1**2*8
    assert abs(g.Mass()-expected)<1e-4,(g.Mass(),expected)
    ex=TopExp_Explorer(readback,TopAbs_SOLID);n=0
    while ex.More():n+=1;ex.Next()
    assert n==1,n
    return {'available':True,'valid':True,'solids':n,'bbox_mm':extents,
            'volume_mm3':g.Mass(),'mass_g_at_2_70':g.Mass()*.0027,
            'thread_model':'B holes are 4.2 mm tap-drill cylinders; tap M5x0.8 per drawing.'}

def verify_dxf(path,geometry=False):
    d=ezdxf.readfile(path);a=d.audit();assert not a.errors,a.errors
    out={'file':path.name,'units':d.units,'audit_errors':len(a.errors)}
    assert d.units==4
    if geometry:
        m=d.modelspace();c=list(m.query('CIRCLE'));assert len(c)==12
        outline=list(m.query('LWPOLYLINE'));assert len(outline)==1 and outline[0].closed
        for layer,expected,r in [('HOLES',A,2.25),('COUNTERBORE',A,4.),('THREAD',B,2.1)]:
            entities=[e for e in c if e.dxf.layer==layer]
            found=sorted((round(e.dxf.center.x,6),round(e.dxf.center.y,6)) for e in entities)
            assert found==sorted(expected),(layer,found)
            assert all(abs(e.dxf.radius-r)<1e-9 for e in entities)
        out.update(circles=12,physical_holes=8,closed_outline=True)
    return out

def main():
    geom=geometry_dxf()
    d=doc_new()
    pdfpath=PDF_DIR/(NAME+'_尺寸与安装.pdf')
    c=canvas.Canvas(str(pdfpath),pagesize=(420*mm,297*mm))
    c.setTitle('SGX滑块-2020立柱转接板 60x60x8 R0')
    c.setAuthor('Codex / project design draft')
    s=Sheet(d,c);frame(s,1,'滑块-2020 立柱紧凑转接板');top_view(s);section(s);hole_table(s)
    c.showPage();s=Sheet(d,c,430);assembly(s);c.showPage();c.save()
    drawing=OUT/(NAME+'_drawing.dxf')
    d.set_modelspace_vport(315,center=(210,148.5));d.saveas(drawing)
    step=make_step()
    # Numerical clearances: all holes separated; no overlap with 2020 footprint.
    clearance=min(math.hypot(x-u,y-v)-4-2.5 for x,y in A for u,v in B)
    assert clearance>8
    assert min(math.hypot(abs(x)-10,abs(y)-10)-4 for x,y in A)>3
    expected=(60*60-(4-math.pi)*4)*8-4*math.pi*(2.25**2*8+(16-2.25**2)*4.5)-4*math.pi*2.1**2*8
    qa={'parameters_mm':P,'slide_holes':A,'bracket_holes':B,
        'dxf':[verify_dxf(geom,True),verify_dxf(drawing)],'step':step,
        'estimated_mass_g':expected*.0027,'min_hole_edge_gap_mm':clearance,
        'assumptions':['Physical slide: 4 x M4 on 30x30 pitch, adequate depth.',
                       '2020 profile; four flat-bottom brackets with bottom hole 10 mm from profile contact face.',
                       'Payload and acceleration unconfirmed; no load rating assigned.']}
    (OUT/'verification.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    readme='''# SGX 滑块 - 2020 立柱转接板 R0

这是依据现有 SGX 图纸绘制的试配设计，外形 60×60×8 mm，材料 6061-T6。
实物滑块型号、M4 螺纹和深度仍须核对；尚未核定载荷/加速度/倾覆力矩。

## 文件
- *_plate_1to1.dxf：真正的 1:1 毫米孔位图；板中心为 (0,0)，八个实体孔。
- *_drawing.dxf：两页 A3 标注图在模型空间并排；中文字体 simhei.ttf。
- *.step：单个实体，Z=0..8 mm；M5 孔以 Ø4.2 底孔表示，必须按图攻丝。
- PDF：两页尺寸与装配说明。
- build_adapter.py：可重建文件的生成脚本。
- verification.json：DXF 回读、几何校验及 STEP 实体回读结果。

## 安装
4×Ø4.5 通孔 + 上面 Ø8 深 4.5 沉孔，用 M4 螺钉拧入滑块外侧 30×30 四孔。
4×M5×0.8 通螺纹孔，中心坐标 (0,±20)、(±20,0)，用于四面角码。
本板不使用中心端面螺钉，不需要给型材端面攻丝。
角码必须平底无凸齿，底孔中心距型材贴合面 10 mm；外伸≤20 mm，宽≤20 mm。
M5 螺钉不得伸出转接板下面；M4 螺钉不得顶到滑块孔底。
立柱约 200 mm 是项目假设，2020 并非已验证的载荷选型。

## 图层（1:1 DXF）
OUTLINE：外形；HOLES：M4 间隙通孔；COUNTERBORE：仅上面圆柱沉孔；THREAD：M5 底孔。
不能把 COUNTERBORE 当作通孔切穿，也不能把 THREAD 当普通 Ø4.2 光孔交货。
圆角 R2；其余去毛刺小倒钝按二维图，STEP 不建去毛刺细节。

## 依据与限制
本地来源：1. 丝杆滑台3D模型/42和57单丝杆滑台模组3D模型/SGX支撑 标准/SGX-正反牙-单边100(1).pdf
外侧四孔距 30×30、M4；60×42 滑块外形依据同目录 SGX STEP 模型。
该厂家资料不证明用户手中实物完全一致。确认后方可按对应孔位加工。
角码孔位是本设计的选配条件，不代表所有 2020 角码通用。
'''
    (OUT/'README_使用说明.md').write_text(readme,encoding='utf-8')
    zpath=OUT/(NAME+'_图纸包.zip')
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        for p in [geom,drawing,pdfpath,OUT/'README_使用说明.md',OUT/'verification.json',Path(__file__)]:z.write(p,p.name)
        step_path=OUT/(NAME+'.step')
        if step['available']:z.write(step_path,step_path.name)
    print(json.dumps(qa,ensure_ascii=False,indent=2))
    print('PDF:',pdfpath)
    print('ZIP:',zpath)

if __name__=='__main__':main()
