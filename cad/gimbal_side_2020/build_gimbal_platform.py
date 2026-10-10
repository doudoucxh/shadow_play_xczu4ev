"""Side-adjustable shelf for supplied 015 gimbal and three photo-sized brackets."""
from pathlib import Path
import sys,os,math,json,zipfile
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tmp'/'ocp_deps'),str(ROOT/'tmp'/'cad_deps')]
from OCP.gp import gp_Pnt,gp_Vec,gp_Dir,gp_Ax2,gp_Trsf,gp_Ax1
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Fuse,BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform,BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.STEPControl import STEPControl_Reader,STEPControl_Writer,STEPControl_AsIs
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE,TopAbs_EDGE,TopAbs_IN,TopAbs_REVERSED
from OCP.TopoDS import TopoDS,TopoDS_Compound
from OCP.BRep import BRep_Builder,BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Line,GeomAbs_Circle
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ColorGen
from OCP.Quantity import Quantity_Color,Quantity_TOC_RGB
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location
import ezdxf
from ezdxf.math import Vec3
from PIL import Image,ImageDraw,ImageFont

NAME='GIMBAL015_side_2020_100x125x10_R0'
MOUNT=[(-25.82,34.75),(25.82,34.75),(25.82,-34.75),(-25.82,-34.75)]
SLOTS=[(0.,-34.,'Y'),(-26.,-60.,'X'),(26.,-60.,'X')]
P=dict(width=100,length=125,thickness=10,corner_radius=2,
       x_bounds=[-50,50],y_bounds=[-75,50],notch_width=22,notch_depth=26,
       notch_front_y=-49,notch_inner_r=2,post_center=[0,-60],post_envelope=[20,20],
       gimbal_hole_diameter=3.4,gimbal_holes=MOUNT,slots=SLOTS,
       through_slot_width=6,through_slot_total_length=18,
       upper_counterbore_slot_width=10,upper_counterbore_slot_length=22,
       upper_counterbore_depth=5.5,slot_end_center_distance=12)

def box(x,y,z,w,l,h):return BRepPrimAPI_MakeBox(gp_Pnt(x,y,z),w,l,h).Shape()
def cyl(x,y,z,r,h,d=(0,0,1)):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(*d)),r,h).Shape()
def cut(a,b):
    q=BRepAlgoAPI_Cut(a,b);q.Build();assert q.IsDone();return q.Shape()
def fuse(a,b):
    q=BRepAlgoAPI_Fuse(a,b);q.Build();assert q.IsDone();return q.Shape()
def unify(s):
    u=ShapeUpgrade_UnifySameDomain(s,True,True,False);u.Build();return u.Shape()
def volume(s):
    g=GProp_GProps();BRepGProp.VolumeProperties_s(s,g);return g.Mass()
def bbox(s):
    b=Bnd_Box();BRepBndLib.AddOptimal_s(s,b,False,False);return list(b.Get())
def solid_list(s):
    result=[];e=TopExp_Explorer(s,TopAbs_SOLID)
    while e.More():result.append(TopoDS.Solid_s(e.Current()));e.Next()
    return result
def transformed(s,t):return BRepBuilderAPI_Transform(s,t,True).Shape()
def read_step(p):
    old=Path.cwd();os.chdir(p.parent)
    try:
        r=STEPControl_Reader();assert r.ReadFile(p.name)==IFSelect_RetDone
        assert r.TransferRoots()>0;return r.OneShape()
    finally:os.chdir(old)
def write_step(s,path,name):
    Interface_Static.SetCVal_s('write.step.schema','AP214IS')
    Interface_Static.SetCVal_s('write.step.unit','MM')
    Interface_Static.SetCVal_s('write.step.product.name',name)
    w=STEPControl_Writer();w.Transfer(s,STEPControl_AsIs)
    old=Path.cwd();os.chdir(path.parent)
    try:assert w.Write(path.name)==IFSelect_RetDone
    finally:os.chdir(old)
def compound(shapes):
    b=BRep_Builder();c=TopoDS_Compound();b.MakeCompound(c)
    for s in shapes:b.Add(c,s)
    return c

def rounded_blank():
    s=fuse(box(-48,-75,0,96,125,10),box(-50,-73,0,100,121,10))
    for x in (-48,48):
        for y in (-73,48):s=fuse(s,cyl(x,y,0,2,10))
    # Rear-open notch, 22 wide, 26 deep; inner corners R2.
    n=fuse(box(-11,-76,-1,22,25,12),box(-9,-51,-1,18,2,12))
    for x in (-9,9):n=fuse(n,cyl(x,-51,-1,2,12))
    return unify(cut(s,n))

def capsule(x,y,axis,width,z,height):
    r=width/2
    if axis=='X':
        s=box(x-6,y-r,z,12,width,height)
        for dx in (-6,6):s=fuse(s,cyl(x+dx,y,z,r,height))
    else:
        s=box(x-r,y-6,z,width,12,height)
        for dy in (-6,6):s=fuse(s,cyl(x,y+dy,z,r,height))
    return unify(s)

def build_plate():
    blank=rounded_blank();p=blank
    for x,y in MOUNT:p=cut(p,cyl(x,y,-1,1.7,12))
    for x,y,axis in SLOTS:
        p=cut(p,capsule(x,y,axis,6,-1,12))
        p=cut(p,capsule(x,y,axis,10,4.5,6.5))
    return unify(p),blank

def photo_bracket():
    # Reference envelope only: photo provides 20 x 28 x 28, wall 3, hole 6.
    # Hole centres 16 from outer corner are assumptions accommodated by slots.
    s=fuse(box(-10,0,-3,20,28,3),box(-10,0,-28,20,3,28))
    for x in (-10,7):
        poly=BRepBuilderAPI_MakePolygon()
        for p in ((x,3,-3),(x,28,-3),(x,3,-28)):poly.Add(gp_Pnt(*p))
        poly.Close();face=BRepBuilderAPI_MakeFace(poly.Wire()).Face()
        s=fuse(s,BRepPrimAPI_MakePrism(face,gp_Vec(3,0,0)).Shape())
    s=cut(s,cyl(0,16,-4,3,5))
    s=cut(s,cyl(0,-1,-16,3,5,(0,1,0)))
    return unify(s)

def load_reference():
    src=ROOT/'015 简易二维云台图纸'/'三维STEP通用格式'/'简易云台.STEP'
    original=read_step(src);solids=solid_list(original)
    assert len(solids)==61
    base=compound(solids[:2]);b=bbox(base)
    xmin=b[0];cy=(b[1]+b[4])/2;cz=(b[2]+b[5])/2
    assert abs(b[4]-b[1]-88)<1e-5 and abs(b[5]-b[2]-90)<1e-5
    # Supplied assembly has its upright along +X; map +X to new +Z.
    tr=gp_Trsf();tr.SetValues(0,1,0,-cy,0,0,1,-cz,1,0,0,10-xmin)
    ref=transformed(original,tr);ref_solids=solid_list(ref)
    transformed_base=compound(ref_solids[:2])
    # Establish that selected source holes actually pass through the bottom
    # flanges, rather than inferring it from cylinder axis locations alone.
    exact=[]
    for x,y in MOUNT:
        sol=ref_solids[0] if x>0 else ref_solids[1]
        inside=lambda xx,yy,z:BRepClass3d_SolidClassifier(sol,gp_Pnt(xx,yy,z),1e-7).State()==TopAbs_IN
        assert not inside(x,y,10.5),(x,y,'blocked centre')
        assert inside(x+1.8,y,10.5),(x,y,'missing supporting metal')
        exact.append([math.copysign(25.8166,x),y])
    return ref,transformed_base,dict(source=str(src),base_footprint_mm=[88,90],
        source_vertical_axis='+X',transformed_vertical_axis='+Z',
        bottom_flange_thickness_mm=2,selected_source_holes=exact,
        rounded_plate_hole_centres=MOUNT,max_hole_rounding_offset_mm=.0034,
        source_base_origin=[xmin,cy,cz])

def positioned_parts(ref):
    parts=[('GIMBAL015_REFERENCE',ref,(.45,.53,.60))]
    post=box(-10,-70,-100,20,20,200)
    parts.append(('2020_POST_ENVELOPE_ONLY',post,(.68,.70,.72)))
    bracket=photo_bracket()
    for label,deg,dx,dy in [('FRONT',0,0,-50),('LEFT',90,-10,-60),('RIGHT',-90,10,-60)]:
        t=gp_Trsf();t.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),math.radians(deg))
        t.SetTranslationPart(gp_Vec(dx,dy,0))
        parts.append((f'2020_BRACKET_{label}_PHOTO_ENVELOPE_ASSUMED_HOLES',transformed(bracket,t),(.65,.67,.70)))
    return parts

def outline_entities(blank):
    ex=TopExp_Explorer(blank,TopAbs_FACE);face=None
    while ex.More():
        f=TopoDS.Face_s(ex.Current());surf=BRepAdaptor_Surface(f)
        if surf.GetType()==GeomAbs_Plane and abs(surf.Plane().Axis().Direction().Z())>.999:
            b=bbox(f)
            if abs(b[2])<1e-6 and abs(b[5])<1e-6:face=f;break
        ex.Next()
    assert face is not None
    wire=BRepTools.OuterWire_s(face);ex=TopExp_Explorer(wire,TopAbs_EDGE);entities=[]
    while ex.More():
        cv=BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()));a=cv.FirstParameter();b=cv.LastParameter()
        p=cv.Value(a);q=cv.Value(b)
        if cv.GetType()==GeomAbs_Line:entities.append(('LINE',[p.X(),p.Y()],[q.X(),q.Y()]))
        elif cv.GetType()==GeomAbs_Circle:
            cir=cv.Circle();c=cir.Location();mid=cv.Value((a+b)/2)
            angle=lambda p:math.degrees(math.atan2(p.Y()-c.Y(),p.X()-c.X()))%360
            start,end,m=angle(p),angle(q),angle(mid)
            if (m-start)%360>(end-start)%360:start,end=end,start
            entities.append(('ARC',[c.X(),c.Y()],cir.Radius(),start,end))
        else:raise AssertionError(cv.GetType())
        ex.Next()
    return entities

def export_2d(blank):
    doc=ezdxf.new('R2010');doc.units=4
    layers={'OUTLINE':7,'GIMBAL_M3_THRU':1,'M5_SLOT_THRU':3,'M5_SLOT_TOP_POCKET_D5P5':5}
    for name,color in layers.items():doc.layers.new(name,dxfattribs={'color':color})
    m=doc.modelspace()
    for e in outline_entities(blank):
        if e[0]=='LINE':m.add_line(e[1],e[2],dxfattribs={'layer':'OUTLINE'})
        else:m.add_arc(e[1],e[2],e[3],e[4],dxfattribs={'layer':'OUTLINE'})
    for x,y in MOUNT:m.add_circle((x,y),1.7,dxfattribs={'layer':'GIMBAL_M3_THRU'})
    for x,y,axis in SLOTS:
        for width,layer in ((6,'M5_SLOT_THRU'),(10,'M5_SLOT_TOP_POCKET_D5P5')):
            r=width/2;attrs={'layer':layer}
            if axis=='X':
                m.add_line((x-6,y-r),(x+6,y-r),dxfattribs=attrs)
                m.add_line((x-6,y+r),(x+6,y+r),dxfattribs=attrs)
                m.add_arc((x+6,y),r,270,90,dxfattribs=attrs)
                m.add_arc((x-6,y),r,90,270,dxfattribs=attrs)
            else:
                m.add_line((x-r,y-6),(x-r,y+6),dxfattribs=attrs)
                m.add_line((x+r,y-6),(x+r,y+6),dxfattribs=attrs)
                m.add_arc((x,y+6),r,0,180,dxfattribs=attrs)
                m.add_arc((x,y-6),r,180,360,dxfattribs=attrs)
    doc.set_modelspace_vport(145,center=(0,-12.5))
    p=OUT/(NAME+'_2D_1to1.dxf');doc.saveas(p)
    back=ezdxf.readfile(p);assert not back.audit().errors and back.units==4
    assert len(list(back.modelspace().query('CIRCLE[layer=="GIMBAL_M3_THRU"]')))==4
    return p

def assembly_step(parts):
    d=TDocStd_Document(TCollection_ExtendedString('BinXCAF'))
    st=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());ct=XCAFDoc_DocumentTool.ColorTool_s(d.Main())
    for name,s,color in parts:
        lab=st.AddShape(s,False);TDataStd_Name.Set_s(lab,TCollection_ExtendedString(name))
        ct.SetColor(lab,Quantity_Color(*color,Quantity_TOC_RGB),XCAFDoc_ColorGen)
    w=STEPCAFControl_Writer();w.SetColorMode(True);w.SetNameMode(True)
    assert w.Transfer(d,STEPControl_AsIs)
    p=OUT/(NAME+'_assembly_reference.step');old=Path.cwd();os.chdir(OUT)
    try:assert w.Write(p.name)==IFSelect_RetDone
    finally:os.chdir(old)
    return p

def mesh_faces(shape):
    t=BRepMesh_IncrementalMesh(shape,.10,False,.3,True);t.Perform()
    ex=TopExp_Explorer(shape,TopAbs_FACE);out=[]
    while ex.More():
        f=TopoDS.Face_s(ex.Current());loc=TopLoc_Location();mesh=BRep_Tool.Triangulation_s(f,loc)
        for j in range(1,mesh.NbTriangles()+1):
            ids=list(mesh.Triangle(j).Get())
            if f.Orientation()==TopAbs_REVERSED:ids[1],ids[2]=ids[2],ids[1]
            vs=[]
            for k in ids:
                p=mesh.Node(k).Transformed(loc.Transformation());vs.append(Vec3(p.X(),p.Y(),p.Z()))
            no=(vs[1]-vs[0]).cross(vs[2]-vs[0])
            if no.magnitude>1e-10:out.append((vs,no.normalize()))
        ex.Next()
    return out

def preview(parts,plate):
    # Technical render directly from CAD surfaces, without generative imagery.
    cached=[(name,mesh_faces(s),tuple(int(c*255) for c in color)) for name,s,color in parts]
    im=Image.new('RGB',(1900,1200),'white');dr=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',n)
    dr.text((40,25),'015 云台侧装平台 / 100×125×10 mm / 不攻丝',font=font(30),fill='black')
    panels=[(Vec3(1,1,.75).normalize(),Vec3(-1,1,0).normalize(),Vec3(0,-15,25),4.0,550,620,True),
            (Vec3(1,1,-1.1).normalize(),Vec3(-1,1,0).normalize(),Vec3(0,-45,-15),3.4,1390,490,False)]
    for n,right,center,scale,cx,cy,with_gimbal in panels:
        up=n.cross(right).normalize();faces=[]
        for name,triangles,col in cached:
            if not with_gimbal and name=='GIMBAL015_REFERENCE':continue
            for vs,no in triangles:
                if no.dot(n)<=1e-8:continue
                pts=[(cx+(v-center).dot(right)*scale,cy-(v-center).dot(up)*scale) for v in vs]
                light=.50+.50*max(0,no.dot((n+Vec3(-.2,.1,.1)).normalize()))
                faces.append((sum(v.dot(n) for v in vs)/3,pts,tuple(int(c*light) for c in col)))
        for _,pts,col in sorted(faces,key=lambda x:x[0]):dr.polygon(pts,fill=col)
    dr.text((1170,945),'仰视：三只角件支撑安装板',font=font(25),fill='black')
    dr.text((40,1110),'角件外形按图片建模，孔中心距暂按 16 mm；板上长圆孔允许 10～22 mm 调整。',font=font(23),fill='black')
    dr.text((40,1150),'立柱为 20×20 外包络示意；只核对原始姿态，不代表舵机全行程无干涉。',font=font(23),fill='black')
    p=OUT/(NAME+'_assembly_preview.png');im.save(p);return p

def main():
    plate,blank=build_plate();assert BRepCheck_Analyzer(plate).IsValid()
    assert len(solid_list(plate))==1
    # Independent nominal volume including the two radiused notch corners.
    area=100*125-(4-math.pi)*2**2-(22*26-2*(1-math.pi/4)*2**2)
    nominal=area*10-4*math.pi*1.7**2*10
    thru=6*12+math.pi*3**2;pocket=10*12+math.pi*5**2
    nominal-=3*(thru*10+(pocket-thru)*5.5)
    assert abs(volume(plate)-nominal)<1e-4,(volume(plate),nominal)
    stp=OUT/(NAME+'_plate.step');write_step(plate,stp,NAME+'_NO_TAPPED_HOLES')
    back=read_step(stp);assert BRepCheck_Analyzer(back).IsValid() and len(solid_list(back))==1
    assert abs(volume(back)-volume(plate))<1e-4
    ref,base,source=load_reference();parts=positioned_parts(ref)
    collisions={}
    for name,s,color in parts:
        v=abs(volume(BRepAlgoAPI_Common(plate,s).Shape()))
        collisions['plate__'+name]=v;assert v<1e-5,(name,v)
    post=parts[1][1]
    collisions['gimbal__post_current_pose']=abs(volume(BRepAlgoAPI_Common(ref,post).Shape()))
    assert collisions['gimbal__post_current_pose']<1e-5
    parts=[('PLATE_100x125x10_NO_TAPPED_HOLES',plate,(.34,.60,.76))]+parts
    assy=assembly_step(parts);dxf=export_2d(blank);png=preview(parts,plate)
    qa=dict(parameters_mm=P,plate_step_valid=True,plate_solid_count=1,
            plate_bbox_mm=bbox(back),volume_mm3=volume(back),aluminium_mass_g=volume(back)*.0027,
            source_mounting_interface=source,collision_volumes_mm3=collisions,
            limitations=['Bracket hole centres and rib shape are approximate from photo.',
                         'Post is 20x20 envelope only; actual slot and T-nut not modelled.',
                         'No full-range servo motion or dynamic load validation.'])
    (OUT/(NAME+'_verification.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
    note=f'''# 015 云台侧装平台 R0

- 加工件：100×125×10 mm，6061-T6 铝合金；约 {volume(plate)*.0027:.1f} g，不含其它零件。
- 全部孔不攻丝。后侧 22 mm 开口绕过 2020 立柱；立柱中心 (0,-60)。
- 坐标原点为云台 88×90 mm 底座中心，而非新板几何中心。X 范围 -50～50，Y 范围 -75～50。
- 云台使用原底座已有的 4 个 φ3 孔；新板对应 4×φ3.4，位置 (±25.82,±34.75)。
- 孔位由用户 STEP 中实际底面核查；原 X 方向竖直，装配文件已转为 Z 方向竖直。

## 三只角件和高度调整
采用图片的 2020 角件，外形 20×28×28 mm，壁厚 3 mm，孔宽约 6 mm。
前方一只、左右各一只，均在板下面；竖直面通过 M5 螺钉和匹配实际槽型的 T 形螺母接立柱。
松开这三处竖直连接后，托住整层并沿型材上下移动，调好后重新锁紧。

角件图片未给孔中心距。参考模型暂用距外侧贴合面 16 mm；板上长圆槽使中心距 10～22 mm 可调，
但角件实际孔位、筋条和工具空间仍须试装，参考角件不能当作供应商精确模型。
每处下层通槽 6×18、端半径 R3；上面沉槽 10×22、端半径 R5、深 5.5；两层圆弧中心距均为 12。
上沉槽用于容纳 M5 圆柱头（常见头高 5、头径约 8.5），螺母及垫圈在角件内部。

## 安装次序
1. 先把三只角件用 T 形螺母松装到立柱合适高度。
2. 由板上方将三颗 M5 内六角圆柱头螺钉穿过沉槽、通槽和角件，下面加垫圈、螺母。
   先紧固板与角件，保持板面水平；使用能伸入角件两筋之间的工具。
3. 再放入原云台底座。四颗 M3 螺钉从板底向上穿，螺母在原云台底座内部。
   初选 M3×16、M5×16 均需按实际垫圈/螺母试配；不能顶住上方零件。
4. 锁紧三处与立柱相连的 T 形螺母。以后调高度只松这三处，不需要拆云台。

前方 M5 沉槽在云台底座下方，装云台后上方工具通道会被遮挡，所以必须先安装平台与角件。
安装板 STEP 是精确加工实体；装配 STEP 含用户原云台、简化角件和立柱外包络，仅作装配参考。
装配中立柱 200 mm 长、平台位于中间是示意；未规定最终层高。
已检查原始姿态下板与云台、立柱、角件之间没有实体穿透；未验证舵机全部角度或动态承载。

## 文件
- *_plate.step：本次需要加工的安装板。
- *_assembly_reference.step：装配参考，角件和立柱是简化件。
- *_2D_1to1.dxf：毫米，1:1；OUTLINE 外形，GIMBAL_M3_THRU 通孔，
  M5_SLOT_THRU 通槽，M5_SLOT_TOP_POCKET_D5P5 上面沉槽。不同深度不能一并切穿。
- PDF：沿用黑白尺寸工程图；正式加工以其中尺寸和公差为准。

规格参考：https://www.accu.co.uk/metric-cap-head-screws/1010037-NBK-SNSP-M5-16-R360
实际紧固件选择普通合适材质即可；该链接只用于核对头部尺寸。
'''
    (OUT/(NAME+'_安装说明.md')).write_text(note,encoding='utf8')
    print(json.dumps(qa,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
