"""Plain A3 vector engineering drawing of the side-mounted gimbal plate."""
from pathlib import Path
import sys,json,math
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'output'/'cad'/'adapter_2020'))
import build_engineering_pdf as draw
import build_gimbal_platform as model
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from pypdf import PdfReader

PDF=ROOT/'output'/'pdf'/(model.NAME+'_engineering_A3.pdf')
TMP=ROOT/'tmp'/'pdfs'/'gimbal_side_R0';TMP.mkdir(parents=True,exist_ok=True)

def capsule(cx,cy,width,length,axis='X',scale=1):
    r=width/2*scale;span=(length-width)/2*scale
    C=draw.C;C.setLineWidth(.35)
    if axis=='X':
        draw.line(cx-span,cy-r,cx+span,cy-r,.35);draw.line(cx-span,cy+r,cx+span,cy+r,.35)
        C.arc(cx+span-r,cy-r,cx+span+r,cy+r,startAng=270,extent=180)
        C.arc(cx-span-r,cy-r,cx-span+r,cy+r,startAng=90,extent=180)
    else:
        draw.line(cx-r,cy-span,cx-r,cy+span,.35);draw.line(cx+r,cy-span,cx+r,cy+span,.35)
        C.arc(cx-r,cy+span-r,cx+r,cy+span+r,startAng=0,extent=180)
        C.arc(cx-r,cy-span-r,cx+r,cy-span+r,startAng=180,extent=180)

def main_view(blank):
    cx,cy=85,205
    for e in model.outline_entities(blank):
        if e[0]=='LINE':draw.line(cx+e[1][0],cy+e[1][1],cx+e[2][0],cy+e[2][1],.45)
        else:
            center,r,a,b=e[1:];draw.C.setLineWidth(.45)
            draw.C.arc(cx+center[0]-r,cy+center[1]-r,cx+center[0]+r,cy+center[1]+r,startAng=a,extent=(b-a)%360)
    draw.line(cx-54,cy,cx+54,cy,.16,[6,1,1,1])
    draw.line(cx,cy-80,cx,cy+54,.16,[6,1,1,1])
    draw.text(cx+55,cy+1,'+X',2.7);draw.text(cx+2,cy+54,'+Y',2.7)
    draw.text(cx+2,cy+2,'O',2.7,white=True)
    for i,(x,y) in enumerate(model.MOUNT):
        px,py=cx+x,cy+y;draw.circle(px,py,1.7);draw.centremark(px,py,2)
        draw.text(px+4,py+3,f'A{i+1}',2.9,white=True)
    for i,(x,y,axis) in enumerate(model.SLOTS):
        px,py=cx+x,cy+y
        capsule(px,py,6,18,axis);capsule(px,py,10,22,axis)
        draw.line(px-13,py,px+13,py,.15,[4,1,.7,1])
        draw.line(px,py-13,px,py+13,.15,[4,1,.7,1])
        dx,dy=(7,0) if i==0 else (0,-11)
        draw.text(px+dx,py+dy,f'B{i+1}',2.9,white=True)
    # Reference only: actual profile slot geometry is intentionally omitted.
    draw.C.saveState();draw.C.setLineWidth(.18);draw.C.setDash([2,1])
    draw.C.rect(cx-10,cy-70,20,20,stroke=1,fill=0);draw.C.restoreState()
    draw.text(cx+2,cy-60,'P',2.8,white=True)
    draw.dimh(cx-50,cx+50,cy+50,268,'100±0.10')
    draw.dimv(cy-75,cy+50,cx-50,23,'125±0.10')
    draw.dimh(cx-25.82,cx+25.82,cy+36.45,248,'(51.64)',2.9)
    draw.dimv(cy-34.75,cy+34.75,cx+27.52,124,'(69.50)',2.9)
    draw.dimh(cx-11,cx+11,cy-75,121,'22 +0.20/0',3.0)
    draw.dimv(cy-75,cy-49,cx+11,149,'26±0.10',3.0)
    draw.text(cx,111,'上视图（云台安装面）  1:1',3.5,'center')

def coordinate_table():
    x,y,w,h=180,203,100,64
    C=draw.C;C.setLineWidth(.25);C.rect(x,y,w,h,stroke=1,fill=0)
    for xx in (198,226,254):draw.line(xx,y,xx,y+h,.18)
    for yy in range(211,267,8):draw.line(x,yy,x+w,yy,.18)
    draw.text(230,275,'孔 / 槽中心坐标（mm）',3.5,'center')
    for xx,s in ((189,'编号'),(212,'X'),(240,'Y'),(267,'长轴')):draw.text(xx,261.5,s,3.1,'center')
    rows=[(f'A{i+1}',x,y,'圆孔') for i,(x,y) in enumerate(model.MOUNT)]
    rows += [(f'B{i+1}',x,y,axis) for i,(x,y,axis) in enumerate(model.SLOTS)]
    for i,(label,x,y,axis) in enumerate(rows):
        yy=253.5-i*8
        f=lambda v:'0' if v==0 else f'{v:+.2f}'
        for xx,s in ((189,label),(212,f(x)),(240,f(y)),(267,axis)):draw.text(xx,yy,s,3.1,'center')
    draw.text(180,195,'O：原云台底座中心；孔 / 槽中心公差 ±0.05。',2.9)
    draw.text(180,189,'A1-A4：4×φ3.4 +0.15/0 通孔，配 M3。',3.1)
    draw.text(180,183,'B1-B3：3 处阶梯长圆槽，均不攻丝。',3.1)

def slot_detail():
    cx,cy,s=346,215,3
    capsule(cx,cy,6,18,'X',s);capsule(cx,cy,10,22,'X',s)
    draw.line(cx-39,cy,cx+39,cy,.16,[6,1,1,1])
    for x in (cx-18,cx+18):draw.line(x,cy-19,x,cy+19,.16,[6,1,1,1])
    draw.dimh(cx-33,cx+33,cy+15,242,'22 +0.20/0',3.1)
    draw.dimh(cx-27,cx+27,cy-9,188,'18 +0.20/0',3.1)
    draw.dimv(cy-9,cy+9,cx+27,389,'6 +0.20/0',3.0)
    draw.dimv(cy-15,cy+15,cx+33,403,'10 +0.20/0',3.0)
    draw.text(cx,264,'B 槽局部详图  3:1',3.5,'center')
    draw.text(303,177,'通槽：6×18，端部 R3。',3.1)
    draw.text(303,171,'上沉槽：10×22，端部 R5，深 5.5。',3.1)
    draw.text(303,165,'两层圆弧中心距均为 12（参考）。',3.0)

def cross_section():
    cx,by,s=226,119,3
    points=[(-9,0),(-3,0),(-3,4.5),(-5,4.5),(-5,10),(-9,10),
            (-9,6),(-9.45,5.5),(-8.55,4.5),(-9,4)]
    transform=lambda x,z:(cx+x*s,by+z*s)
    draw.hatched_polygon([transform(x,z) for x,z in points])
    draw.hatched_polygon([transform(-x,z) for x,z in reversed(points)])
    draw.line(cx,by-3,cx,by+33,.15,[6,1,.7,1])
    draw.dimh(cx-15,cx+15,by+30,159,'10 +0.20/0',3.1)
    draw.dimh(cx-9,cx+9,by,108,'6 +0.20/0',3.1)
    draw.dimv(by,by+30,cx-27,188,'10±0.10',3.1)
    draw.dimv(by+13.5,by+30,cx+27,267,'5.5 +0.20/0',3.0)
    draw.text(cx,96,'B 槽横剖（垂直长轴）  3:1',3.5,'center')

def bracket_notes():
    for i,s in enumerate([
        '角件接口：3×2020 角件（外购）',
        '图片外形 20×28×28，壁厚 3，孔宽约 6。',
        '角件孔中心距未标，装配模型暂按 16。',
        '本板允许距型材贴合面 10～22 调整。',
        '实测角件孔位应落在长圆槽范围内。',
        '上下调高通过立柱槽内 T 形螺母完成。',
    ]):draw.text(295,144-i*7,s,3.1 if i else 3.4)

def title_notes():
    notes=[
        '技术要求：',
        '1. 单位 mm。材料 6061-T6；全部孔不攻丝。',
        '2. 原点 O 为云台底座中心。板边 X=±50；Y=-75、+50。',
        '3. 外轮廓四角 R2±0.20；开口前端两内角 R2±0.20。',
        '4. 立柱开口宽 22、深 26。P=(0,-60)，虚线仅为立柱包络，不加工。',
        '5. 两装配面各自平面度 0.10；去毛刺，锐边轻倒钝。',
        '6. A 孔配原云台底座，实际对孔后装 M3 螺钉和螺母。',
        '7. B 上沉槽从云台侧加工，容纳 M5 圆柱头，头部不得高于板面。',
        '8. 公差已标项目按标注；未注线性尺寸 ±0.10。按尺寸加工，勿量图。',
        '装配：先装三只角件和安装板，再装云台，避免遮住前方螺钉工具通道。',
        '调高：托住整层，松开角件与立柱的三个连接点，上下移动后重新锁紧。',
        '核对：角件孔位 / 筋条 / 工具空间需实物试装；尚未校核全角度运动及动态载荷。',
    ]
    for i,s in enumerate(notes):draw.text(14,96-i*6.2,s,3.0 if i else 3.5)
    x,y,w,h=220,10,190,41;C=draw.C
    C.setLineWidth(.35);C.rect(x,y,w,h,stroke=1,fill=0)
    for yy in (19,29,39):draw.line(x,yy,x+w,yy,.22)
    draw.line(372,29,372,39,.22)
    for xx in (285,341,375):draw.line(xx,19,xx,29,.22)
    draw.line(337,10,337,19,.22)
    draw.text(315,43,'015 云台 - 2020 侧装平台',4.3,'center')
    draw.text(223,32.5,'图号：G015-SIDE-100125-10',3.1)
    draw.text(391,32.5,'版本 R0',3.1,'center')
    draw.text(223,22.5,'材料：6061-T6',3.1)
    draw.text(313,22.5,'比例 1:1 / 3:1',3.0,'center')
    draw.text(358,22.5,'单位 mm',3.0,'center')
    draw.text(392,22.5,'A3  1/1',3.0,'center')
    draw.text(223,13,'试制图 / 角件接口待实测',3.1)
    draw.text(340,13,'日期：2026-09-28',3.1)

def main():
    plate,blank=model.build_plate()
    assert model.BRepCheck_Analyzer(plate).IsValid()
    draw.C=canvas.Canvas(str(PDF),pagesize=(420*mm,297*mm),pageCompression=1)
    C=draw.C;draw.TEXTS=[];C.setTitle('015 云台侧装平台 - 不攻丝尺寸工程图')
    C.setAuthor('');C.scale(mm,mm);C.setFillColorRGB(0,0,0);C.setStrokeColorRGB(0,0,0)
    C.setLineWidth(.5);C.rect(10,10,400,277,stroke=1,fill=0)
    main_view(blank);coordinate_table();slot_detail();cross_section();bracket_notes();title_notes()
    for x,y,w,h,s in draw.TEXTS:
        assert x>=10 and x+w<=410 and y>=10 and y+h<=287,(x,y,w,h,s)
    C.showPage();C.save()
    pdf=PdfReader(PDF);assert len(pdf.pages)==1
    text=pdf.pages[0].extract_text()
    for s in ('100±0.10','125±0.10','10±0.10','φ3.4','25.82','34.75','5.5','不攻丝','6061-T6'):
        assert s in text,s
    (TMP/'verification.json').write_text(json.dumps(dict(pdf=str(PDF),pages=1,
        paper_mm=[420,297],dimension_text_verified=True,text_in_frame=True),ensure_ascii=False,indent=2),encoding='utf8')
    print(str(PDF))

if __name__=='__main__':main()
