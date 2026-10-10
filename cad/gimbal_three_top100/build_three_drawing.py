"""Two plain A3 sheets: common plate manufacturing and top-100 assembly layout."""
from pathlib import Path
import sys,json,math
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'output/cad/gimbal_side_2020_direct'))
import build_direct_drawing as old
import build_three_platforms as model
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from pypdf import PdfReader
draw=old.draw
PDF=ROOT/'output/pdf'/(model.NAME+'_engineering_A3.pdf')
TMP=ROOT/'tmp/pdfs/gimbal_three_R3'

def outline(blank,cx,cy,scale=1,angle=0,post_offset=0,invert=False,width=.4):
    a=math.radians(angle);c,s=math.cos(a),math.sin(a);k=-1 if invert else 1
    def pt(x,y):
        y+=post_offset
        return cx+k*scale*(c*x-s*y),cy+k*scale*(s*x+c*y)
    for e in model.lib.outline_entities(blank):
        if e[0]=='LINE':draw.line(*pt(*e[1]),*pt(*e[2]),width)
        else:
            center,r,aa,bb=e[1:];x,y=pt(*center);r*=scale
            draw.C.setLineWidth(width)
            draw.C.arc(x-r,y-r,x+r,y+r,startAng=aa+angle+(180 if invert else 0),extent=(bb-aa)%360)

def plate_view(blank):
    cx,cy,s=119,248.5,1.5
    outline(blank,cx,cy,s)
    draw.line(53,cy,185,cy,.16,[6,1,1,1]);draw.line(cx,103,cx,276,.16,[6,1,1,1])
    draw.text(187,cy+1,'+X',2.7);draw.text(cx+2,273,'+Y',2.7);draw.text(cx+2,cy+2,'O',2.7,white=True)
    for i,((x,y),(dx,dy)) in enumerate(zip(model.MOUNT,[(5,-6),(5,3),(5,3),(-10,3)])):
        px,py=cx+s*x,cy+s*y;draw.circle(px,py,1.7*s);draw.centremark(px,py,2)
        draw.text(px+dx,py+dy,f'A{i+1}',2.7,white=True)
    for i,(x,y,axis) in enumerate(model.SLOTS):
        px,py=cx+s*x,cy+s*y
        old.prev.old.capsule(px,py,6,18,axis,s);old.prev.old.capsule(px,py,10,22,axis,s)
        draw.line(px-19,py,px+19,py,.15,[5,1,.7,1]);draw.line(px,py-10,px,py+10,.15,[5,1,.7,1])
        draw.text(px,111,f'B{i+1}',2.8,'center',white=True)
    C=draw.C;C.saveState();C.setDash([2,1]);C.setLineWidth(.18)
    C.rect(104,107.5,30,30,stroke=1,fill=0);C.restoreState();draw.text(122,123,'P',2.8,white=True)
    draw.dimh(86,152,272.5,281,'44±0.10',3)
    draw.dimh(59,179,100,89,'80±0.10',3)
    draw.dimh(99.5,138.5,100,78,'26 +0.20/0',3)
    draw.dimv(100,272.5,59,40,'115±0.10',3)
    draw.dimv(100,137.5,179,190,'25±0.10',3)
    draw.dimv(137.5,181,152,190,'29±0.10',3)
    draw.dimv(100,157,138.5,216,'38±0.10',3)
    draw.text(119,66,'上视图（支架安装面）  3:2',3.4,'center')

def coordinates():
    C=draw.C;C.setLineWidth(.25);C.rect(238,203,169,63,stroke=1,fill=0)
    for xx in (264,309,354):draw.line(xx,203,xx,266,.18)
    for yy in range(212,266,9):draw.line(238,yy,407,yy,.18)
    draw.text(322.5,275,'孔 / 槽中心坐标（mm）',3.5,'center')
    for xx,t in ((251,'编号'),(286.5,'X'),(331.5,'Y'),(380.5,'类型 / 长轴')):draw.text(xx,260,t,3.1,'center')
    rows=[(f'A{i+1}',x,y,'圆孔') for i,(x,y) in enumerate(model.MOUNT)]
    rows += [(f'B{i+1}',x,y,axis) for i,(x,y,axis) in enumerate(model.SLOTS)]
    for i,(label,x,y,axis) in enumerate(rows):
        fmt=lambda v:'0.00' if v==0 else f'{v:+.2f}'
        for xx,t in ((251,label),(286.5,fmt(x)),(331.5,fmt(y)),(380.5,axis)):draw.text(xx,251-i*9,t,3.1,'center')
    draw.text(238,195,'A1-A4：4×φ3.4 +0.15/0 通孔，配 M3。',3.1)
    draw.text(238,189,'O：四颗支架底部螺钉孔组中心；坐标公差 ±0.05。',2.9)

def title_block(page):
    C=draw.C;C.setLineWidth(.35);C.rect(220,10,190,41,stroke=1,fill=0)
    for yy in (19,29,39):draw.line(220,yy,410,yy,.22)
    draw.line(372,29,372,39,.22)
    for xx in (285,341,375):draw.line(xx,19,xx,29,.22)
    draw.line(337,10,337,19,.22)
    name='015 三层云台通用平台板' if page==1 else '015 三层云台安装位置图'
    draw.text(315,43,name,4.1,'center');draw.text(223,32.5,'图号：G015-TOP100-80115-10',3.1)
    draw.text(391,32.5,'版本 R3',3.1,'center')
    draw.text(223,22.5,'6061-T6 / 数量 3' if page==1 else '型材顶部 100 mm 安装区',2.9)
    draw.text(313,22.5,'比例 3:2 / 3:1' if page==1 else '安装位置示意',2.9,'center')
    draw.text(358,22.5,'单位 mm',3,'center');draw.text(392,22.5,f'A3  {page}/2',3,'center')
    draw.text(223,13,'试制图 / 角件接口待实测',3.1);draw.text(340,13,'日期：2026-09-28',3.1)

def plate_notes():
    notes=[
        '技术要求：单位 mm；材料 6061-T6；全部孔不攻丝；同款加工 3 件。',
        '1. O 为四孔组中心；板边 Y=-99、+16。外轮廓各转角均 R2±0.20。',
        '2. 斜边理论端点：(±40,-74) 与 (±22,-45)，25 / 29 定位理论交点。',
        '3. 未注线性公差 ±0.10；孔 / 槽中心坐标公差 ±0.05。',
        '4. 开口宽 26、深 38，内角 R2±0.20；P=(0,-84)，虚线不加工。',
        '5. 两装配面各自平面度 0.10；去毛刺，锐边轻倒钝。',
        '6. B 上沉槽朝上，M5 圆柱头不得高于板面，下方配螺母。',
        '7. A 孔对应舵机固定支架底孔；支架底面直接贴板。',
        '8. 不与 R2 混用槽位和外形；按标注尺寸加工，勿量图。',
    ]
    for i,t in enumerate(notes):draw.text(14,59-i*5.25,t,2.8)
    right=[
        'B1 / B2：阶梯长圆槽',
        '通槽 6×18，端部 R3。',
        '上沉槽 10×22，端部 R5。',
        '从安装面加工，深 5.5。',
        '两层圆弧中心距 12（参考）。',
        '槽宽 / 总长公差 +0.20/0。',
        '每层 2×2020 角件，共 6 个。',
        '外形 20×28×28，壁厚 3。',
        '图片未标孔距，模型暂按 16。',
        '槽允许距贴合面 10～22。',
        '角件实际筋条 / 孔位需核对。',
        '三层安装方向和标高见第 2 页。',
    ]
    for i,t in enumerate(right):draw.text(319,174-i*6.2,t,3.0 if i else 3.3)
    for i,t in enumerate(['装配参考：每层 4×M3×16 从支架侧向下穿板，',
                           '板下配薄垫圈和螺母，实际头高与长度需试配。',
                           '先固定支架，再装回下舵机，确保螺丝刀能进入。',
                           '三层紧凑，调高后必须重新检查相邻层间隙。',
                           '未验证完整转动范围、杆件、线缆及动态载荷。']):draw.text(238,83-i*6.5,t,3)

def assembly_front(ref):
    cx,cy,s=105,180,.7
    # Front view is from +Y: screen right is -X. Cloud boxes are expressly envelopes.
    C=draw.C;C.setLineWidth(.4);C.rect(cx-7,40,14,140,stroke=1,fill=0)
    draw.line(cx,36,cx,267,.15,[5,1,1,1])
    draw.line(31,110,211,110,.16,[2,1]);draw.line(31,180,211,180,.16,[2,1])
    draw.dimv(110,180,31,20,'100 安装区',3.1)
    for layer in model.LAYERS:
        tr=model.placement(layer)
        b=model.lib.bbox(model.lib.transformed(ref,tr))
        x=cx-b[3]*s;y=cy+b[2]*s;w=(b[3]-b[0])*s;h=(b[5]-b[2])*s
        C.saveState();C.setDash([2,1]);C.setLineWidth(.25);C.rect(x,y,w,h,stroke=1,fill=0);C.restoreState()
        draw.text(x+w/2,y+h+3,layer['cn'],3.1,'center')
        z=layer['z'];top=cy+(z+10)*s;bottom=cy+z*s
        if layer['label']=='CENTRE_MID':xmin,xmax=-40,40
        elif layer['label']=='LEFT_LOW':xmin,xmax=-15,100
        else:xmin,xmax=-100,15
        xx1,xx2=cx-xmax*s,cx-xmin*s
        draw.hatched_polygon([(xx1,bottom),(xx2,bottom),(xx2,top),(xx1,top)])
        if layer['label']=='CENTRE_MID':
            for sign in (-1,1):
                a=(cx+sign*7,bottom);b=(cx+sign*26.6,bottom);c=(cx+sign*7,bottom-19.6)
                draw.line(*a,*b,.3);draw.line(*b,*c,.3);draw.line(*c,*a,.3)
        else:
            C.setLineWidth(.25);C.rect(cx-7,bottom-19.6,14,19.6,stroke=1,fill=0)
        draw.line(xx2,top,210,top,.18,[2,1]);draw.text(212,top+1,f'{z+10:+.0f}' if z+10 else '0 柱顶',3)
    draw.dimv(136.6,158.3,180,194,'31',3)
    draw.dimv(158.3,180,180,194,'31',3)
    draw.text(105,28,'正视位置示意（虚线框为云台包络）',3.1,'center')
    draw.text(105,22,'立柱示意长 200；角件轮廓简化表示。',2.9,'center')

def assembly_table():
    C=draw.C;C.setLineWidth(.25);C.rect(238,220,169,40,stroke=1,fill=0)
    columns=[238,269,300,337,372,407]
    for xx in columns[1:-1]:draw.line(xx,220,xx,260,.18)
    for yy in (230,240,250):draw.line(238,yy,407,yy,.18)
    centres=[(a+b)/2 for a,b in zip(columns,columns[1:])]
    for xx,t in zip(centres,['平台','伸出方向','板上表面 Z','板下表面 Z','柱连接孔 Z']):draw.text(xx,254,t,2.6,'center')
    rows=[['左 / 低','左侧','-62','-72','-88'],['中 / 中','前方','-31','-41','-57'],['右 / 高','右侧','0','-10','-26']]
    for i,row in enumerate(rows):
        for xx,t in zip(centres,row):draw.text(xx,244-i*10,t,3.1,'center')
    draw.text(322.5,275,'三层安装标高（mm）',3.6,'center')
    draw.text(238,211,'Z=0 为型材顶端；向下为负。云台允许高出顶端。',3)
    draw.text(238,204,'角件竖直边朝下；三层板与角件均在 Z=-100～0 内。',3)
    draw.text(238,197,'柱连接孔标高按角件孔距 16 计算，需按实物核对。',3)
    draw.text(238,190,'每层用一对相对槽面，三层合计使用四个槽面。',3)

def assembly_plan(blank):
    cx,cy,s=316,143,.6
    for layer in model.LAYERS:
        outline(blank,cx,cy,s,layer['angle'],84,True,.32)
        a=math.radians(layer['angle']);gx=-84*math.sin(a);gy=84*math.cos(a)
        px,py=cx-s*gx,cy-s*gy
        draw.centremark(px,py,3)
        label={'LEFT_LOW':'L / -62','CENTRE_MID':'M / -31','RIGHT_HIGH':'R / 0'}[layer['label']]
        draw.text(px+5,py+4,label,3.1,white=True)
    draw.hatched_polygon([(310,137),(322,137),(322,149),(310,149)])
    draw.dimh(265.6,316,143,180,'84',3)
    draw.dimh(316,366.4,143,180,'84',3)
    draw.text(316,71,'俯视：中间平台向前，左右平台向两侧',3.0,'center')
    draw.text(238,63,'同款板 3 件；每层 2 个角件，先装低层再装高层。',3)
    draw.text(238,57,'本图为安装位置；全行程运动及动态承载另行核对。',3)

def frame():
    C=draw.C;C.scale(mm,mm);C.setFillColorRGB(0,0,0);C.setStrokeColorRGB(0,0,0)
    C.setLineWidth(.5);C.rect(10,10,400,277,stroke=1,fill=0);draw.TEXTS=[]

def finish_page():
    for x,y,w,h,t in draw.TEXTS:
        assert x>=10 and x+w<=410 and y>=10 and y+h<=287,(x,y,w,h,t)
    draw.C.showPage()

def main():
    _,blank=model.build_plate();ref,_,_=model.r2.load_direct_reference()
    TMP.mkdir(parents=True,exist_ok=True)
    draw.C=canvas.Canvas(str(PDF),pagesize=(420*mm,297*mm),pageCompression=1)
    draw.C.setTitle('015 三层云台 - 顶部100mm安装 - R3 工程图');draw.C.setAuthor('')
    frame();plate_view(blank);coordinates();old.prev.cross_section();plate_notes();title_block(1);finish_page()
    frame();assembly_front(ref);assembly_table();assembly_plan(blank);title_block(2);finish_page()
    draw.C.save();pdf=PdfReader(PDF);assert len(pdf.pages)==2
    text='\n'.join(p.extract_text() for p in pdf.pages)
    for t in ('80±0.10','115±0.10','44±0.10','26 +0.20/0','38±0.10','φ3.4','-84.00','-62','-31','-100','数量 3'):
        assert t in text,t
    (TMP/'verification.json').write_text(json.dumps(dict(pdf=str(PDF),pages=2,paper_mm=[420,297],
        dimension_text_verified=True,text_in_frame=True),ensure_ascii=False,indent=2),encoding='utf8')
    print(str(PDF))

if __name__=='__main__':main()
