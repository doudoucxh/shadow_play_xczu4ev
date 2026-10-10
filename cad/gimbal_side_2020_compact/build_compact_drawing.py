"""Plain dimensioned A3 drawing for the compact two-bracket platform."""
from pathlib import Path
import sys,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'output'/'cad'/'gimbal_side_2020'))
import build_platform_drawing as old
import build_compact_platform as model
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from pypdf import PdfReader
draw=old.draw
PDF=ROOT/'output'/'pdf'/(model.NAME+'_engineering_A3.pdf')
TMP=ROOT/'tmp'/'pdfs'/'gimbal_compact_R1'

def main_view(blank):
    cx,cy,s=119,204,2
    for e in model.lib.outline_entities(blank):
        if e[0]=='LINE':
            draw.line(cx+s*e[1][0],cy+s*e[1][1],cx+s*e[2][0],cy+s*e[2][1],.45)
        else:
            center,r,a,b=e[1:];draw.C.setLineWidth(.45)
            draw.C.arc(cx+s*(center[0]-r),cy+s*(center[1]-r),
                       cx+s*(center[0]+r),cy+s*(center[1]+r),startAng=a,extent=(b-a)%360)
    draw.line(21,cy,217,cy,.16,[6,1,1,1])
    draw.line(cx,92,cx,264,.16,[6,1,1,1])
    draw.text(218,cy+1,'+X',2.7);draw.text(cx+2,263,'+Y',2.7)
    draw.text(cx+2,cy+2,'O',2.7,white=True)
    for i,(x,y) in enumerate(model.MOUNT):
        px,py=cx+s*x,cy+s*y
        draw.circle(px,py,3.4);draw.centremark(px,py,2.5)
        draw.text(px+5,py+4,f'A{i+1}',2.9,white=True)
    for i,(x,y,axis) in enumerate(model.SLOTS):
        px,py=cx+s*x,cy+s*y
        old.capsule(px,py,6,18,axis,s);old.capsule(px,py,10,22,axis,s)
        draw.line(px-25,py,px+25,py,.15,[5,1,.7,1])
        draw.line(px,py-13,px,py+13,.15,[5,1,.7,1])
        draw.text(px,101,f'B{i+1}',3,'center',white=True)
    C=draw.C;C.saveState();C.setLineWidth(.18);C.setDash([2,1])
    C.rect(99,98,40,40,stroke=1,fill=0);C.restoreState()
    draw.text(122,119,'P',2.8,white=True)
    draw.dimh(24,214,258,275,'95±0.10')
    draw.dimv(88,258,24,16,'85±0.10')
    draw.dimh(49.5,188.5,239.64,250,'(69.50)',3)
    draw.dimv(211.64,239.64,188.5,203,'(14.00)',3)
    draw.dimh(97,141,88,79,'22 +0.20/0',3)
    draw.dimv(88,140,141,225,'26±0.10',3)
    draw.text(119,68,'上视图（云台安装面）  2:1',3.5,'center')

def coordinate_table():
    x,y,w,h=238,203,169,63
    C=draw.C;C.setLineWidth(.25);C.rect(x,y,w,h,stroke=1,fill=0)
    for xx in (264,309,354):draw.line(xx,y,xx,y+h,.18)
    for yy in range(212,266,9):draw.line(x,yy,x+w,yy,.18)
    draw.text(322.5,275,'孔 / 槽中心坐标（mm）',3.5,'center')
    for xx,t in ((251,'编号'),(286.5,'X'),(331.5,'Y'),(380.5,'类型 / 长轴')):
        draw.text(xx,260,t,3.1,'center')
    rows=[(f'A{i+1}',x,y,'圆孔') for i,(x,y) in enumerate(model.MOUNT)]
    rows += [(f'B{i+1}',x,y,axis) for i,(x,y,axis) in enumerate(model.SLOTS)]
    for i,(label,x,y,axis) in enumerate(rows):
        yy=251-i*9
        for xx,t in ((251,label),(286.5,f'{x:+.2f}'),(331.5,f'{y:+.2f}'),(380.5,axis)):
            draw.text(xx,yy,t,3.1,'center')
    draw.text(238,195,'A1-A4：4×φ3.4 +0.15/0 通孔，配 M3。',3.1)
    draw.text(238,189,'O：保留半边底座中心；孔 / 槽中心坐标公差 ±0.05。',2.9)

def cross_section():
    cx,by,s=270,124,3
    points=[(-9,0),(-3,0),(-3,4.5),(-5,4.5),(-5,10),(-9,10),
            (-9,6),(-9.45,5.5),(-8.55,4.5),(-9,4)]
    transform=lambda x,z:(cx+x*s,by+z*s)
    draw.hatched_polygon([transform(x,z) for x,z in points])
    draw.hatched_polygon([transform(-x,z) for x,z in reversed(points)])
    draw.line(cx,by-3,cx,by+33,.15,[6,1,.7,1])
    draw.dimh(cx-15,cx+15,by+30,165,'10 +0.20/0',3.1)
    draw.dimh(cx-9,cx+9,by,113,'6 +0.20/0',3.1)
    draw.dimv(by,by+30,cx-27,234,'10±0.10',3.1)
    draw.dimv(by+13.5,by+30,cx+27,305,'5.5 +0.20/0',3)
    draw.text(cx,99,'B 槽横剖（2 处相同）  3:1',3.3,'center')

def interface_notes():
    notes=[
        'B1 / B2：阶梯长圆槽',
        '通槽 6×18，端部 R3。',
        '上沉槽 10×22，端部 R5。',
        '从安装面加工，深 5.5。',
        '两层圆弧中心距 12（参考）。',
        '槽宽 / 总长公差 +0.20/0。',
        '2×2020 角件（外购）',
        '外形 20×28×28，壁厚 3。',
        '图片未标孔距，模型暂按 16。',
        '本板允许距贴合面 10～22。',
        '角件分居立柱左右两侧。',
        'T 形螺母沿立柱槽上下调高。',
    ]
    for i,t in enumerate(notes):draw.text(319,174-i*6.2,t,3.0 if i else 3.3)
    draw.text(238,77,'装配：先装角件和平台，再装保留的云台。',3)
    draw.text(238,71,'调高：托住整层，松开两个立柱连接点，',3)
    draw.text(238,65,'沿槽上下移动后重新锁紧。',3)

def title_notes():
    notes=[
        '技术要求：单位 mm；材料 6061-T6；全部孔不攻丝。',
        '1. 原点 O 为保留底座中心；板边 X=±47.5，Y=-58、+27。',
        '2. 未注线性公差 ±0.10；孔 / 槽中心坐标公差 ±0.05。',
        '3. 外轮廓 4×R2±0.20；开口两内角 R2±0.20。',
        '4. P=(0,-43)；虚线为 2020 立柱包络，不加工。',
        '5. 两装配面各自平面度 0.10；去毛刺，锐边轻倒钝。',
        '6. B 沉槽朝上，M5 圆柱头不得高于板面；下方配螺母。',
        '7. 仅拆空置 U 底座及两半连接件，保留舵机安装件。',
        '8. 按尺寸加工，勿量图；R1 替代 R0 平台孔位方案。',
    ]
    for i,t in enumerate(notes):draw.text(14,59-i*5.25,t,2.9)
    draw.text(238,57,'角件需实物试装；未校核全角度运动及动态载荷。',2.9)
    x,y,w,h=220,10,190,41;C=draw.C
    C.setLineWidth(.35);C.rect(x,y,w,h,stroke=1,fill=0)
    for yy in (19,29,39):draw.line(x,yy,x+w,yy,.22)
    draw.line(372,29,372,39,.22)
    for xx in (285,341,375):draw.line(xx,19,xx,29,.22)
    draw.line(337,10,337,19,.22)
    draw.text(315,43,'015 云台紧凑侧装平台',4.3,'center')
    draw.text(223,32.5,'图号：G015-COMPACT-9585-10',3.1)
    draw.text(391,32.5,'版本 R1',3.1,'center')
    draw.text(223,22.5,'材料：6061-T6',3.1)
    draw.text(313,22.5,'比例 2:1 / 3:1',3,'center')
    draw.text(358,22.5,'单位 mm',3,'center')
    draw.text(392,22.5,'A3  1/1',3,'center')
    draw.text(223,13,'试制图 / 角件接口待实测',3.1)
    draw.text(340,13,'日期：2026-09-28',3.1)

def main():
    plate,blank=model.build_plate()
    assert model.lib.BRepCheck_Analyzer(plate).IsValid()
    PDF.parent.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True)
    draw.C=canvas.Canvas(str(PDF),pagesize=(420*mm,297*mm),pageCompression=1)
    C=draw.C;draw.TEXTS=[];C.setTitle('015 云台紧凑侧装平台 - R1 不攻丝工程图')
    C.setAuthor('');C.scale(mm,mm);C.setFillColorRGB(0,0,0);C.setStrokeColorRGB(0,0,0)
    C.setLineWidth(.5);C.rect(10,10,400,277,stroke=1,fill=0)
    main_view(blank);coordinate_table();cross_section();interface_notes();title_notes()
    for x,y,w,h,t in draw.TEXTS:
        assert x>=10 and x+w<=410 and y>=10 and y+h<=287,(x,y,w,h,t)
    C.showPage();C.save()
    pdf=PdfReader(PDF);assert len(pdf.pages)==1
    extracted=pdf.pages[0].extract_text()
    for t in ('95±0.10','85±0.10','10±0.10','φ3.4','34.75','17.82','3.82','5.5','不攻丝','6061-T6'):
        assert t in extracted,t
    (TMP/'verification.json').write_text(json.dumps(dict(pdf=str(PDF),pages=1,
        paper_mm=[420,297],dimension_text_verified=True,text_in_frame=True),ensure_ascii=False,indent=2),encoding='utf8')
    print(str(PDF))

if __name__=='__main__':main()
