"""R1: retain the servo-supporting U-base; two opposite-face 2020 brackets."""
from pathlib import Path
import sys,math,json,itertools
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'output'/'cad'/'gimbal_side_2020'))
import build_gimbal_platform as lib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from PIL import Image,ImageDraw,ImageFont
from ezdxf.math import Vec3

NAME='GIMBAL015_compact_2020_95x85x10_R1'
MOUNT=[(-34.75,17.82),(34.75,17.82),(34.75,3.82),(-34.75,3.82)]
SLOTS=[(-26.,-43.,'X'),(26.,-43.,'X')]
P=dict(width=95,length=85,thickness=10,x_bounds=[-47.5,47.5],y_bounds=[-58,27],
       corner_radius=2,notch_width=22,notch_depth=26,notch_front_y=-32,notch_inner_r=2,
       post_center=[0,-43],gimbal_base_size=[90,44],gimbal_hole_diameter=3.4,
       gimbal_holes=MOUNT,slots=SLOTS,through_slot_width=6,through_slot_total_length=18,
       upper_counterbore_slot_width=10,upper_counterbore_slot_length=22,
       upper_counterbore_depth=5.5,slot_end_center_distance=12,bracket_count=2,
       occupied_profile_faces=['-X','+X'])

def configure_exports():
    lib.OUT=OUT;lib.NAME=NAME;lib.MOUNT=MOUNT;lib.SLOTS=SLOTS

def rounded_blank():
    s=lib.fuse(lib.box(-45.5,-58,0,91,85,10),lib.box(-47.5,-56,0,95,81,10))
    for x in (-45.5,45.5):
        for y in (-56,25):s=lib.fuse(s,lib.cyl(x,y,0,2,10))
    n=lib.fuse(lib.box(-11,-59,-1,22,25,12),lib.box(-9,-34,-1,18,2,12))
    for x in (-9,9):n=lib.fuse(n,lib.cyl(x,-34,-1,2,12))
    return lib.unify(lib.cut(s,n))

def build_plate():
    blank=rounded_blank();p=blank
    for x,y in MOUNT:p=lib.cut(p,lib.cyl(x,y,-1,1.7,12))
    for x,y,axis in SLOTS:
        p=lib.cut(p,lib.capsule(x,y,axis,6,-1,12))
        p=lib.cut(p,lib.capsule(x,y,axis,10,4.5,6.5))
    return lib.unify(p),blank

def load_compact_reference():
    src=ROOT/'015 简易二维云台图纸'/'三维STEP通用格式'/'简易云台.STEP'
    original=lib.read_step(src);old=lib.solid_list(original);assert len(old)==61
    b0=lib.bbox(old[0]);b1=lib.bbox(old[1])
    assert all(abs(a-b)<1e-5 for a,b in zip(
        [b0[3]-b0[0],b0[4]-b0[1],b0[5]-b0[2]],[29,44,90]))
    assert abs(b1[4]-b0[1])<1e-5  # two separate U-bases meet along this plane
    xmin=b0[0];cy=b0[1];cz=(b0[2]+b0[5])/2
    # Original upright +X -> +Z, plus a 90-degree in-plane rotation so the
    # retained 44 mm dimension is the platform's cantilever direction.
    t=lib.gp_Trsf();t.SetValues(0,0,-1,cz,0,1,0,-cy-22,1,0,0,10-xmin)
    shapes=[lib.transformed(s,t) for s in old]
    kept_ids=[0]+list(range(18,61))
    removed_ids=[1]+list(range(2,18))
    assert len(kept_ids)==44 and set(kept_ids).isdisjoint(removed_ids)
    assert sorted(kept_ids+removed_ids)==list(range(61))
    # The removed small parts are the eight bolts and eight nuts joining the
    # bases at Y=-22; servo attachment hardware starts at source solid 19.
    for i in range(2,18):
        b=lib.bbox(shapes[i]);assert b[1]>-29 and b[4]<-15,(i,b)
    base=shapes[0]
    bb=lib.bbox(base)
    assert all(abs(a-b)<1e-5 for a,b in zip(bb,[-45,-22,10,45,22,39]))
    inside=lambda x,y,z:lib.BRepClass3d_SolidClassifier(lib.TopoDS.Solid_s(base),lib.gp_Pnt(x,y,z),1e-7).State()==lib.TopAbs_IN
    for x,y in MOUNT:
        for z in (10.2,11.8):
            assert not inside(x,y,z),(x,y,z,'not a mounting hole')
            assert inside(x+1.8,y,z),(x,y,z,'unsupported hole')
    kept=lib.compound([shapes[i] for i in kept_ids])
    removed=lib.compound([shapes[i] for i in removed_ids])
    info=dict(source=str(src),retained_source_solid_indices=kept_ids,
        removed_source_solid_indices=removed_ids,removed_parts='one empty U-base plus eight joining bolts and eight nuts',
        remaining_source_solids=44,base_footprint_before_mm=[90,88],base_footprint_after_mm=[90,44],
        mounting_hole_pitch_mm=[69.5,14.0],source_hole_y_mm=[3.8166,17.8166],
        drawing_hole_y_mm=[3.82,17.82],max_nominal_hole_rounding_error_mm=.0034,
        retained_base_bbox_mm=bb,original_to_new_transform='Xnew=-Zold+106.5; Ynew=Yold-27.205849; Znew=Xold+63.137934',
        cutting_required=False,retained_servo_support_and_servo_fasteners_unchanged=True)
    return kept,removed,shapes,info

def positioned_parts(ref,plate):
    post=lib.box(-10,-53,-100,20,20,200)
    parts=[('PLATE_95x85x10_NO_TAPPED_HOLES',plate,(.32,.61,.77)),
           ('GIMBAL_KEEP_SERVO_SUPPORTING_HALF',ref,(.48,.56,.64)),
           ('2020_POST_ENVELOPE_ONLY',post,(.67,.69,.71))]
    bracket=lib.photo_bracket()
    for side,deg,x in [('LEFT',90,-10),('RIGHT',-90,10)]:
        t=lib.gp_Trsf();t.SetRotation(lib.gp_Ax1(lib.gp_Pnt(0,0,0),lib.gp_Dir(0,0,1)),math.radians(deg))
        t.SetTranslationPart(lib.gp_Vec(x,-43,0))
        parts.append((f'BRACKET_{side}_PHOTO_ENVELOPE_ASSUMED_HOLES',lib.transformed(bracket,t),(.68,.70,.72)))
    return parts

def draw_panel(dr,meshes,rect,n,right):
    n=Vec3(n).normalize();right=Vec3(right).normalize();up=n.cross(right).normalize()
    assert up.z>=0
    allverts=[v for _,tris,_ in meshes for vs,no in tris for v in vs]
    us=[v.dot(right) for v in allverts];vs=[v.dot(up) for v in allverts]
    u0,u1,v0,v1=min(us),max(us),min(vs),max(vs)
    left,top,width,height=rect;scale=min(width/(u1-u0),height/(v1-v0))
    ox=left+(width-(u1-u0)*scale)/2;oy=top+(height-(v1-v0)*scale)/2
    faces=[]
    for name,tris,col in meshes:
        for verts,no in tris:
            if no.dot(n)<=1e-8:continue
            pts=[(ox+(v.dot(right)-u0)*scale,oy+(v1-v.dot(up))*scale) for v in verts]
            light=.53+.47*max(0,no.dot((n+Vec3(-.20,.15,.1)).normalize()))
            faces.append((sum(v.dot(n) for v in verts)/3,pts,tuple(int(c*light) for c in col)))
    for _,pts,col in sorted(faces,key=lambda v:v[0]):dr.polygon(pts,fill=col)

def make_previews(parts,shapes):
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',n)
    meshes=[(name,lib.mesh_faces(s),tuple(int(v*255) for v in color)) for name,s,color in parts]
    im=Image.new('RGB',(1800,1150),'white');dr=ImageDraw.Draw(im)
    dr.text((35,25),'R1 紧凑侧装平台 / 95×85×10 mm / 两个角件',font=font(30),fill='black')
    draw_panel(dr,meshes,(45,95,840,910),(1,1,.8),(-1,1,0))
    lower=[p for p in meshes if p[0]!='GIMBAL_KEEP_SERVO_SUPPORTING_HALF']
    draw_panel(dr,lower,(950,130,760,740),(1,1,-1.05),(-1,1,0))
    dr.text((960,940),'仰视：仅使用立柱左右两个槽面',font=font(25),fill='black')
    dr.text((35,1065),'保留承托舵机的 U 形底座；拆下另一半及两半之间的连接螺钉，无需切割。',font=font(22),fill='black')
    dr.text((35,1105),'角件为图片尺寸参考模型；当前姿态无穿透，未校核舵机全行程或动态承载。',font=font(22),fill='black')
    assembly_png=OUT/(NAME+'_assembly_preview.png');im.save(assembly_png)
    # An identification view of the unmodified source assembly shows which
    # independent half is removed. No physical or source-file modification.
    im=Image.new('RGB',(1600,1100),'white');dr=ImageDraw.Draw(im)
    dr.text((35,20),'拆除识别图：红色件可拆，蓝色件保留',font=font(30),fill='black')
    green=[('KEEP_BASE',lib.mesh_faces(shapes[0]),(89,151,192))]
    red=[('REMOVE_EMPTY_BASE',lib.mesh_faces(shapes[1]),(206,87,74))]
    hardware=[('REMOVE_JOINING_HARDWARE',lib.mesh_faces(lib.compound(shapes[2:18])),(210,144,71))]
    drive=[('KEEP_SERVO_ASSEMBLY',lib.mesh_faces(lib.compound(shapes[18:])),(144,151,158))]
    draw_panel(dr,green+red+hardware+drive,(35,100,1080,875),(.75,-1,1.2),(1,.75,0))
    for y,s in [(170,'蓝色：承托舵机的半边'),(215,'红色：独立的扩展底座'),(260,'橙色：两半之间的'),(295,'8 颗连接螺钉 + 8 个螺母'),(385,'不拆舵机自身的固定螺钉'),(450,'若实物结构与模型一致，'),(485,'按螺钉连接处拆开即可。')]:
        dr.text((1150,y),s,font=font(23),fill='black')
    dr.text((35,1025),'此图沿用原装配关系标色。紧凑版保留半边底座的原形状，不把整件直接切成两半。',font=font(22),fill='black')
    p=OUT/(NAME+'_removal_guide.png');im.save(p)
    return assembly_png,p

def distance(a,b):
    d=BRepExtrema_DistShapeShape(a,b);d.Perform();assert d.IsDone();return d.Value()

def verify_plate_readback(plate):
    assert lib.BRepCheck_Analyzer(plate).IsValid()
    solids=lib.solid_list(plate);assert len(solids)==1
    bb=lib.bbox(plate);assert all(abs(a-b)<1e-6 for a,b in zip(bb,[-47.5,-58,0,47.5,27,10]))
    inside=lambda x,y,z:lib.BRepClass3d_SolidClassifier(solids[0],lib.gp_Pnt(x,y,z),1e-7).State()==lib.TopAbs_IN
    for x,y in MOUNT:
        for z in (.1,9.9):assert not inside(x,y,z) and inside(x+1.8,y,z)
    for x,y,axis in SLOTS:
        assert inside(x,y+4,4.4) and not inside(x,y+4,4.6)
        for sign in (-1,1):
            assert not inside(x+sign*8.9,y,.1) and inside(x+sign*9.1,y,.1)
            assert not inside(x+sign*10.9,y,9.9) and inside(x+sign*11.1,y,9.9)
    return dict(step_valid=True,solid_count=1,bbox_mm=bb,through_holes_and_slot_depths_verified=True)

def main():
    configure_exports();plate,blank=build_plate()
    area=95*85-(4-math.pi)*4-(22*26-2*(1-math.pi/4)*4)
    expected=area*10-4*math.pi*1.7**2*10-2*((6*12+math.pi*9)*10+((10-6)*12+math.pi*(25-9))*5.5)
    assert abs(lib.volume(plate)-expected)<1e-4
    file=OUT/(NAME+'_plate.step');lib.write_step(plate,file,NAME+'_NO_TAPPED_HOLES')
    back=lib.read_step(file);qa=verify_plate_readback(back)
    ref,removed,shapes,source=load_compact_reference()
    lib.write_step(ref,OUT/(NAME+'_gimbal_compact_reference.step'),'GIMBAL_KEEP_ONE_U_BASE_AND_ALL_SERVO_SUPPORTS')
    parts=positioned_parts(ref,plate)
    collisions={}
    for (an,a,ac),(bn,b,bc) in itertools.combinations(parts,2):
        v=abs(lib.volume(lib.BRepAlgoAPI_Common(a,b).Shape()))
        collisions[an+'__'+bn]=v;assert v<1e-5,(an,bn,v)
    post=parts[2][1];gap=distance(ref,post)
    assert gap>2.0,gap
    assy=lib.assembly_step(parts)
    assert len(lib.solid_list(lib.read_step(assy)))==48
    lib.export_2d(blank);png,removal_png=make_previews(parts,shapes)
    mass=lib.volume(plate)*.0027
    qa.update(parameters_mm=P,source_modification=source,assembly_solid_count=48,
        volume_mm3=lib.volume(plate),aluminium_plate_mass_g=mass,
        old_plate_mass_g=308.5291438163092,plate_mass_reduction_percent=(1-mass/308.5291438163092)*100,
        bounding_rectangle_area_reduction_percent=(1-95*85/(100*125))*100,
        assembly_current_pose_collision_volumes_mm3=collisions,
        gimbal_to_post_minimum_gap_current_pose_mm=gap,
        retained_base_unchanged=True,full_motion_and_dynamic_load_validation=False,
        bracket_hole_centres_are_photo_assumptions=True)
    (OUT/(NAME+'_verification.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
    note=f'''# 015 云台紧凑侧装平台 R1 / 两角件

## 改动和可拆部分
用户 STEP 中底座由两只独立的 U 形板背靠背用螺钉连接，不是一块必须切割的大底板。
保留直接承托舵机的那一只 U 形板；另一只没有安装舵机的板，以及连接两半的 8 颗 M3 螺钉、8 个螺母可从这次装配中移除。
这些螺钉仅指两半底座拼接处，不是舵机或舵机支架的固定螺钉。拆除识别图已用不同颜色标明。
若实物与模型不同，应先核对连接处，不按图片直接锯切。原始厂家模型和旧版 R0 文件均已保留。
被拆半边原来提供更大的独立支撑/安装面积；改为固定在新板上后不再保留该扩展面积。

## 新板
- 外形 95×85×10 mm，6061-T6，全部不攻丝；仅板约 {mass:.1f} g，旧板约 308.5 g。
- 与旧 100×125 mm 板相比，外包矩形面积减少 35.4%。
- 原底座平面 90×88 mm；保留一半后为 90×44 mm。云台整体绕竖轴重新定向，使短边沿悬伸方向。
- 坐标原点 O 为保留半边底座的中心；新板 X=-47.5～+47.5，Y=-58～+27，底面 Z=0。
- 保留云台底座放在 Z=10 面。四个 φ3.4 安装孔坐标见图，孔距 69.50×14.00 mm。
  原模型孔中心 Y=3.8166、17.8166，制图取 3.82、17.82；偏差小于 0.004 mm。
- 立柱中心 P=(0,-43)，避让口 22 宽、26 深，内角 R2；型材为 2020。
- 只用左右两个角件，前后两个槽面留空。上下调高仍通过侧面 M5 螺钉和 T 形螺母实现。
- B1/B2 通槽 6×18，上沉槽 10×22 深 5.5。上沉槽容纳 M5 圆柱头，螺母在角件内部。
- 角件沿用图片的 20×28×28 mm、壁厚 3 mm 外形；孔中心距未标，参考按 16 mm 建模。
  板槽允许距型材贴合面 10～22 mm 对孔，仍须核对角件的真实孔位、筋条及扳手空间。

## 安装
1. 核对实物后，拆下空的半边 U 形底座及其拼接螺钉，保留舵机和承托舵机的完整 U 形板。
2. 两个角件装在立柱相对的左右槽面，松装 T 形螺母；角件水平面向外伸出承托新板。
3. 先用两颗 M5 圆柱头螺钉由上穿入板的沉槽和角件，下面配垫圈、螺母，找平后锁紧。
4. 紧凑云台放在板上，四颗 M3 螺钉由板下面穿入保留底座的已有孔，螺母放在该 U 形底座内部。
5. 调整到所需高度，锁紧两个侧面的 T 形螺母。以后调高时托住整层再松开这两个连接点。
螺钉长度需按实际板厚、垫圈和螺母试配，不能顶到舵机或上层零件。

## 检查范围
已回读 STEP，核对单板尺寸、通孔、沉槽深度、保留底座的实际通孔位置。
装配共 48 个实体：保留的原云台 44 个、板 1 个、立柱包络 1 个、角件 2 个。
已检查新零件之间和当前姿态的云台没有实体穿透；云台到立柱包络最近距离约 {gap:.2f} mm。
没有把这一静态检查当作舵机全角度验证或承载认证；减去扩展底座后还需试装检查刚性及运动范围。
角件和型材是简化参考件，不是供应商精确模型。

## 文件用途
- *_plate.step：需要加工的新安装板。
- *_gimbal_compact_reference.step：移除空半边及拼接五金后的云台，未改动保留零件的形状。
- *_assembly_reference.step：两角件完整装配参考。
- *_2D_1to1.dxf：毫米，通槽与上沉槽分层，沉槽不能切穿。
- PDF：黑白加工尺寸图，R1；不可继续按 R0 的孔位加工。
'''
    (OUT/(NAME+'_安装与拆除说明.md')).write_text(note,encoding='utf8')
    print(json.dumps({k:qa[k] for k in ('bbox_mm','aluminium_plate_mass_g','plate_mass_reduction_percent',
          'bounding_rectangle_area_reduction_percent','gimbal_to_post_minimum_gap_current_pose_mm','assembly_solid_count')},indent=2))

if __name__=='__main__':main()
