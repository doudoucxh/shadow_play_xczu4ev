"""Black-and-white, dimensioned A3 manufacturing drawing of the R2 adapter.

Orthographic views and local sections are analytic vector geometry. Dimensions
are checked against the existing exact STEP before writing the drawing.
"""
from pathlib import Path
import sys, os, math, json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tmp' / 'ocp_deps'))
import build_adapter_10mm as cad
from OCP.GeomAbs import GeomAbs_Cone
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from pypdf import PdfReader

OUT = ROOT / 'output' / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)
TMP = ROOT / 'tmp' / 'pdfs' / 'adapter_R2_engineering'
TMP.mkdir(parents=True, exist_ok=True)
NAME = 'SGX_2020_adapter_60x60x10_R2_notap_engineering_A3'
PDF = OUT / (NAME + '.pdf')
STEP = HERE / 'SGX_2020_adapter_60x60x10_R2_notap.step'
HOLES = [
    ('A1', -15., 15.), ('A2', 15., 15.),
    ('A3', 15., -15.), ('A4', -15., -15.),
    ('B1', 0., 20.), ('B2', 20., 0.),
    ('B3', 0., -20.), ('B4', -20., 0.),
]
P = dict(width=60., length=60., thickness=10., corner_r=2.,
         a_through=4.5, a_cb_d=8., a_cb_depth=4.5,
         b_through=5.5, b_cs_d=11.5, b_cs_angle=90.)


def verify_step():
    previous = Path.cwd()
    os.chdir(HERE)
    try:
        shape = cad.read_step(STEP)
    finally:
        os.chdir(previous)
    assert cad.BRepCheck_Analyzer(shape).IsValid()
    bb = cad.Bnd_Box(); cad.BRepBndLib.Add_s(shape, bb)
    bounds = bb.Get()
    dims = [bounds[i+3]-bounds[i] for i in range(3)]
    assert all(abs(a-b)<1e-5 for a,b in zip(dims, (60,60,10)))
    actual = cad.cylinder_features(shape)
    expected = {(x,y,2.25) for label,x,y in HOLES if label[0]=='A'}
    expected |= {(x,y,4.) for label,x,y in HOLES if label[0]=='A'}
    expected |= {(x,y,2.75) for label,x,y in HOLES if label[0]=='B'}
    expected |= {(x,y,2.) for x in (-28.,28.) for y in (-28.,28.)}
    assert actual == expected, (actual, expected)
    cone_centres = set()
    ex = cad.TopExp_Explorer(shape, cad.TopAbs_FACE)
    while ex.More():
        surf = cad.BRepAdaptor_Surface(cad.TopoDS.Face_s(ex.Current()))
        if surf.GetType()==GeomAbs_Cone:
            cone=surf.Cone(); p=cone.Axis().Location()
            assert abs(abs(cone.SemiAngle())-math.pi/4)<1e-8
            cone_centres.add((round(p.X(),6),round(p.Y(),6)))
        ex.Next()
    assert cone_centres == {(x,y) for label,x,y in HOLES if label[0]=='B'}
    ex = cad.TopExp_Explorer(shape,cad.TopAbs_SOLID)
    solid=cad.TopoDS.Solid_s(ex.Current()); ex.Next(); assert not ex.More()
    inside=lambda x,y,z:cad.BRepClass3d_SolidClassifier(solid,cad.gp_Pnt(x,y,z),1e-7).State()==cad.TopAbs_IN
    for label,x,y in HOLES:
        assert not inside(x,y,.1) and not inside(x,y,9.9)
        if label[0]=='A':
            assert inside(x+3,y,5.49) and not inside(x+3,y,5.51)
        else:
            # Radius at z=1.5 is 4.25; checks both depth and downward opening.
            assert not inside(x+4.24,y,1.5) and inside(x+4.26,y,1.5)
            assert not inside(x+2.74,y,3.1) and inside(x+2.76,y,3.1)
    return dict(step_valid=True, solid_count=1, extents_mm=dims,
                cylinder_locations_and_radii_match=True,
                bottom_countersinks_and_top_counterbores_verified=True)


pdfmetrics.registerFont(TTFont('CN', 'C:/Windows/Fonts/simhei.ttf'))
C = None
TEXTS = []


def line(x1,y1,x2,y2,w=.22,dash=None):
    C.saveState(); C.setLineWidth(w)
    C.setDash(dash or [])
    C.line(x1,y1,x2,y2); C.restoreState()


def text(x,y,s,size=3.2,align='left',white=False):
    width=pdfmetrics.stringWidth(s,'CN',size)
    x0=x-width/2 if align=='center' else x-width if align=='right' else x
    C.saveState()
    if white:
        C.setFillColorRGB(1,1,1); C.rect(x0-.7,y-.7,width+1.4,size+1.1,stroke=0,fill=1)
    C.setFillColorRGB(0,0,0); C.setFont('CN',size); C.drawString(x0,y,s)
    C.restoreState()
    TEXTS.append((x0,y,width,size,s))


def arrow(tip, direction, length=2.2, half=.55):
    x,y=tip; dx,dy=direction
    p=C.beginPath(); p.moveTo(x,y)
    p.lineTo(x+dx*length-dy*half,y+dy*length+dx*half)
    p.lineTo(x+dx*length+dy*half,y+dy*length-dx*half)
    p.close(); C.drawPath(p,stroke=0,fill=1)


def dimh(x1,x2,from_y,at_y,label,size=3.2):
    sign=1 if at_y>from_y else -1
    for x in (x1,x2):line(x,from_y+sign*.8,x,at_y+sign*1.5,.18)
    line(x1,at_y,x2,at_y,.18)
    arrow((x1,at_y),(1,0)); arrow((x2,at_y),(-1,0))
    text((x1+x2)/2,at_y+1.3,label,size,'center',True)


def dimv(y1,y2,from_x,at_x,label,size=3.2):
    sign=1 if at_x>from_x else -1
    for y in (y1,y2):line(from_x+sign*.8,y,at_x+sign*1.5,y,.18)
    line(at_x,y1,at_x,y2,.18)
    arrow((at_x,y1),(0,1)); arrow((at_x,y2),(0,-1))
    C.saveState(); C.translate(at_x-1.5,(y1+y2)/2); C.rotate(90)
    width=pdfmetrics.stringWidth(label,'CN',size)
    C.setFillColorRGB(1,1,1); C.rect(-width/2-.7,-.6,width+1.4,size+1,stroke=0,fill=1)
    C.setFillColorRGB(0,0,0); C.setFont('CN',size); C.drawString(-width/2,0,label)
    C.restoreState()


def circle(x,y,r,hidden=False):
    C.saveState(); C.setLineWidth(.18 if hidden else .35)
    C.setDash([1.8,1.1] if hidden else [])
    C.circle(x,y,r,stroke=1,fill=0); C.restoreState()


def centremark(x,y,r):
    line(x-r-1.6,y,x+r+1.6,y,.15,[3,1,.6,1])
    line(x,y-r-1.6,x,y+r+1.6,.15,[3,1,.6,1])


def view(cx,cy,bottom=False):
    s=2.
    C.saveState(); C.setLineWidth(.45)
    C.roundRect(cx-30*s,cy-30*s,60*s,60*s,2*s,stroke=1,fill=0)
    C.restoreState()
    line(cx-64,cy,cx+64,cy,.18,[7,1.2,1,1.2])
    line(cx,cy-64,cx,cy+64,.18,[7,1.2,1,1.2])
    for label,x,y in HOLES:
        px=cx+x*s; py=cy+(-y if bottom else y)*s
        if label[0]=='A':
            circle(px,py,4.5/2*s)
            circle(px,py,8/2*s,hidden=bottom)
            centremark(px,py,8/2*s)
        else:
            circle(px,py,5.5/2*s)
            circle(px,py,11.5/2*s,hidden=not bottom)
            centremark(px,py,11.5/2*s)
        if not bottom:
            offsets={'A1':(9,7),'A2':(9,7),'A3':(9,-9),'A4':(9,-9),
                     'B1':(13,0),'B2':(13,6),'B3':(10,-10),'B4':(-15,6)}
            ox,oy=offsets[label];text(px+ox,py+oy,label,2.8,white=True)
    if not bottom:
        text(cx+65,cy+1,'+X',2.6);text(cx+2,cy+64,'+Y',2.6)
        text(cx+2,cy+2,'O',2.6,white=True)


def hatched_polygon(points):
    p=C.beginPath();p.moveTo(*points[0])
    for v in points[1:]:p.lineTo(*v)
    p.close()
    C.saveState(); C.clipPath(p,stroke=0,fill=0)
    xmin=min(x for x,y in points);xmax=max(x for x,y in points)
    ymin=min(y for x,y in points);ymax=max(y for x,y in points)
    a=math.floor((xmin-ymax)/3.2)*3.2
    while a<=xmax-ymin:
        line(a+ymin,ymin,a+ymax,ymax,.14)
        a+=3.2
    C.restoreState();C.setLineWidth(.35);C.drawPath(p,stroke=1,fill=0)


def section(cx,bottom,kind):
    s=4.;T=lambda x,z:(cx+x*s,bottom+z*s)
    if kind=='A':
        left=[(-7,0),(-2.25,0),(-2.25,5.5),(-4,5.5),(-4,10),
              (-7,10),(-7,6),(-7.45,5.5),(-6.55,4.5),(-7,4)]
    else:
        left=[(-9,0),(-5.75,0),(-2.75,3),(-2.75,10),
              (-9,10),(-9,6),(-9.45,5.5),(-8.55,4.5),(-9,4)]
    hatched_polygon([T(x,z) for x,z in left])
    hatched_polygon([T(-x,z) for x,z in reversed(left)])
    line(cx,bottom-3,cx,bottom+43,.15,[6,1,.6,1])
    if kind=='A':
        dimh(cx-16,cx+16,bottom+40,133,'φ8 +0.20/0')
        dimh(cx-9,cx+9,bottom,75,'φ4.5 +0.15/0')
        dimv(bottom,bottom+40,cx-28,46,'10±0.10')
        dimv(bottom+22,bottom+40,cx+28,121,'4.5 +0.20/0',3.0)
        text(cx,62,'A 孔局部剖视  4:1','3.5' if False else 3.5,'center')
    else:
        dimh(cx-11,cx+11,bottom+40,133,'φ5.5 +0.15/0')
        dimh(cx-23,cx+23,bottom,75,'φ11.5 +0.20/0')
        text(cx,bottom+5.7,'90°±0.5°',3.0,'center',True)
        text(cx+39,bottom+36,'上面',2.8)
        text(cx+39,bottom+.5,'下面',2.8)
        text(cx,62,'B 孔局部剖视  4:1',3.5,'center')


def table():
    x,y,w,h=320,213,86,63
    C.setLineWidth(.25);C.rect(x,y,w,h,stroke=1,fill=0)
    for xx in (342,374):line(xx,y,xx,y+h,.18)
    for yy in range(220,276,7):line(x,yy,x+w,yy,.18)
    text(363,280,'孔中心坐标（上视图，mm）',3.2,'center')
    for xc,s in ((331,'孔号'),(358,'X'),(390,'Y')):text(xc,271,s,3.2,'center')
    for i,(label,hx,hy) in enumerate(HOLES):
        yy=264-i*7
        for xc,s in ((331,label),(358,f'{hx:+.0f}' if hx else '0'),(390,f'{hy:+.0f}' if hy else '0')):
            text(xc,yy,s,3.2,'center')
    text(320,199,'A1-A4：4 处相同',3.5)
    text(320,192,'4×φ4.5 +0.15/0 通孔')
    text(320,186,'上面：φ8 +0.20/0')
    text(320,180,'圆柱沉孔，深 4.5 +0.20/0')
    text(320,174,'孔距（30×30），参考',3.0)
    text(320,165,'B1-B4：4 处相同',3.5)
    text(320,158,'4×φ5.5 +0.15/0 通孔')
    text(320,152,'下面：φ11.5 +0.20/0')
    text(320,146,'锥形沉孔，90°±0.5°')
    text(320,140,'理论深 3（参考），不攻丝',3.0)
    text(320,117,'上面：朝向角码 / 立柱',3.2)
    text(320,111,'下面：贴合滑块',3.2)
    text(320,99,'虚线圆表示另一面的沉孔。',3.0)
    text(320,93,'全部孔均不攻丝。',3.5)


def notes_and_title():
    notes=[
        '技术要求：',
        '1. 单位 mm。外形及厚度公差 ±0.10；四角 R2±0.20。',
        '2. 孔中心坐标公差 ±0.05；原点 O 为板几何中心。',
        '3. 两装配面各自平面度 0.10；去毛刺，锐边轻倒钝。',
        '4. 沉头座面不得大倒角；用 90° M5 沉头螺栓试配，头部不得凸出下面。',
        '5. 加工前核对滑块 M4 四孔 30×30 孔距及角码孔位；实物接口尚未确认。',
        '6. 本图对应 R2 不攻丝版；按标注尺寸加工，不得量图取数。',
    ]
    for i,s in enumerate(notes):text(14,49-i*5.5,s,3.0 if i else 3.5)
    x,y,w,h=220,10,190,41
    C.setLineWidth(.35);C.rect(x,y,w,h,stroke=1,fill=0)
    for yy in (19,29,39):line(x,yy,x+w,yy,.22)
    line(372,29,372,39,.22)
    for xx in (285,341,375):line(xx,19,xx,29,.22)
    line(337,10,337,19,.22)
    text(315,43,'滑块 - 2020 立柱转接板',4.3,'center')
    text(223,32.5,'图号：SGX-ADP-2020-10-N',3.1)
    text(391,32.5,'版本 R2',3.1,'center')
    text(223,22.5,'材料：6061-T6',3.1)
    text(313,22.5,'比例 2:1 / 4:1',3.0,'center')
    text(358,22.5,'单位 mm',3.0,'center')
    text(392,22.5,'A3  1/1',3.0,'center')
    text(223,13,'试制图 / 接口待核对',3.1)
    text(340,13,'日期：2026-09-27',3.1)


def main():
    global C
    qa=verify_step()
    C=canvas.Canvas(str(PDF),pagesize=(420*mm,297*mm),pageCompression=1)
    C.setTitle('60x60x10 R2 不攻丝转接板 - 尺寸工程图')
    C.setSubject('A3 black-and-white engineering drawing; units mm; no tapped holes')
    C.setAuthor('')
    C.scale(mm,mm);C.setStrokeColorRGB(0,0,0);C.setFillColorRGB(0,0,0)
    C.setLineWidth(.5);C.rect(10,10,400,277,stroke=1,fill=0)
    view(83,211)
    view(243,211,True)
    dimh(23,143,271,280,'60±0.10')
    dimv(151,271,23,16,'60±0.10')
    dimh(53,113,249,265,'(30)',3.0)
    line(24.17,269.83,20,275,.18)
    line(20,275,62,275,.18)
    v=(20-24.17,275-269.83);n=math.hypot(*v)
    arrow((24.17,269.83),(v[0]/n,v[1]/n))
    text(26,276,'4×R2±0.20',3.0)
    text(83,142,'上视图（上面朝向立柱）  2:1',3.5,'center')
    text(243,142,'下视图（沿 X 轴翻转 180°）  2:1',3.5,'center')
    section(83,84,'A');section(243,84,'B')
    table();notes_and_title()
    # Catch text escaping the printable frame; visual QA follows separately.
    for x,y,w,h,s in TEXTS:
        assert x>=10 and x+w<=410 and y>=10 and y+h<=287,(x,y,w,h,s)
    C.showPage();C.save()
    reader=PdfReader(PDF);assert len(reader.pages)==1
    page=reader.pages[0];body=page.extract_text()
    for label,x,y in HOLES:assert label in body
    for required in ('60±0.10','10±0.10','φ4.5','φ5.5','φ11.5','90°±0.5°','不攻丝','6061-T6'):
        assert required in body,required
    assert abs(float(page.mediabox.width)/mm-420)<.001
    assert abs(float(page.mediabox.height)/mm-297)<.001
    qa.update(pdf=str(PDF),page_count=1,paper_mm=[420,297],
              no_tapped_holes=True,dimensions_mm=P,hole_table=HOLES,
              all_required_dimension_text_present=True,text_within_frame=True)
    (TMP/'drawing_verification.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(qa,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
