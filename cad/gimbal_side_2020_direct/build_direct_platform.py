"""R2 direct mounts the original servo holder to a no-tap 80x85x10 plate."""
from pathlib import Path
import sys,math,json,itertools,zipfile
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'output/cad/gimbal_side_2020_compact'))
import build_compact_platform as prev
lib=prev.lib
from PIL import Image,ImageDraw,ImageFont

NAME='GIMBAL015_direct_2020_80x85x10_R2'
MOUNT=[(0.,-7.),(7.,0.),(0.,7.),(-7.,0.)]
SLOTS=[(-26.,-54.,'X'),(26.,-54.,'X')]
P=dict(width=80,length=85,thickness=10,x_bounds=[-40,40],y_bounds=[-69,16],
       corner_radius=2,notch_width=22,notch_depth=26,notch_front_y=-43,notch_inner_r=2,
       origin='centre of the four original bottom holder bolts',post_center=[0,-54],
       gimbal_hole_diameter=3.4,gimbal_holes=MOUNT,slots=SLOTS,
       through_slot_width=6,through_slot_total_length=18,
       upper_counterbore_slot_width=10,upper_counterbore_slot_length=22,
       upper_counterbore_depth=5.5,slot_end_center_distance=12,bracket_count=2,
       holder_bottom_z=10,holder_foot_thickness=2,height_reduction_from_R1=29)

def configure_exports():
    lib.OUT=OUT;lib.NAME=NAME;lib.MOUNT=MOUNT;lib.SLOTS=SLOTS

def rounded_blank():
    s=lib.fuse(lib.box(-38,-69,0,76,85,10),lib.box(-40,-67,0,80,81,10))
    for x in (-38,38):
        for y in (-67,14):s=lib.fuse(s,lib.cyl(x,y,0,2,10))
    n=lib.fuse(lib.box(-11,-70,-1,22,25,12),lib.box(-9,-45,-1,18,2,12))
    for x in (-9,9):n=lib.fuse(n,lib.cyl(x,-45,-1,2,12))
    return lib.unify(lib.cut(s,n))

def build_plate():
    blank=rounded_blank();p=blank
    for x,y in MOUNT:p=lib.cut(p,lib.cyl(x,y,-1,1.7,12))
    for x,y,axis in SLOTS:
        p=lib.cut(p,lib.capsule(x,y,axis,6,-1,12))
        p=lib.cut(p,lib.capsule(x,y,axis,10,4.5,6.5))
    return lib.unify(p),blank

def load_direct_reference():
    _,_,r1_shapes,source=prev.load_compact_reference()
    t=lib.gp_Trsf();t.SetTranslation(lib.gp_Vec(0,-10.8166,-29))
    shapes=[lib.transformed(s,t) for s in r1_shapes]
    kept_ids=[18]+list(range(27,61))
    ref=lib.compound([shapes[i] for i in kept_ids]);holder=shapes[18]
    inside=lambda x,y,z:lib.BRepClass3d_SolidClassifier(lib.TopoDS.Solid_s(holder),lib.gp_Pnt(x,y,z),1e-7).State()==lib.TopAbs_IN
    for x,y in MOUNT:
        for z in (10.1,11.9):
            assert not inside(x,y,z) and inside(x+1.65,y,z),(x,y,z)
    assert abs(lib.bbox(holder)[2]-10)<1e-7
    source=dict(source=source['source'],retained_source_solid_indices=kept_ids,
        removed_source_solid_indices=list(range(18))+list(range(19,27)),
        removed='both large U-bases, their joining fasteners, and original four short holder bolts/nuts',
        retained='original fixed servo holder (solid 18) and all servo/upper-axis parts (27..60)',
        holder_bolt_coordinates=MOUNT,holder_foot_thickness_mm=2,holder_bottom_z=10,
        original_holder_bolts_under_head_length_mm=8,replacement_under_head_length_mm=16,
        height_reduction_from_R1_mm=29,cutting_required=False,
        source_retained_shapes_unchanged=True,origin='original four lower holder bolt pattern centre',
        R1_to_R2_translation_mm=[0,-10.8166,-29])
    return ref,shapes,source

def hex_nut(x,y,z):
    r=5.5/math.sqrt(3);p=lib.BRepBuilderAPI_MakePolygon()
    for i in range(6):
        a=math.radians(30+60*i);p.Add(lib.gp_Pnt(x+r*math.cos(a),y+r*math.sin(a),z))
    p.Close();face=lib.BRepBuilderAPI_MakeFace(p.Wire()).Face()
    s=lib.BRepPrimAPI_MakePrism(face,lib.gp_Vec(0,0,2.4)).Shape()
    return lib.cut(s,lib.cyl(x,y,z-.1,1.6,2.6))

def new_fasteners(shapes):
    # Reuse only original screw heads. New unthreaded reference shanks are 16 long.
    original_screws=[shapes[i] for i in (19,21,22,23)]
    parts=[]
    for i,((x,y),old) in enumerate(zip(MOUNT,original_screws),1):
        head=lib.BRepAlgoAPI_Common(old,lib.box(x-4,y-4,12,8,8,4)).Shape()
        bolt=lib.unify(lib.fuse(head,lib.cyl(x,y,-4,1.5,16.01)))
        assert len(lib.solid_list(bolt))==1
        washer=lib.cut(lib.cyl(x,y,-.5,3.5,.5),lib.cyl(x,y,-.6,1.6,.7))
        nut=hex_nut(x,y,-2.9)
        parts.extend([(f'M3x16_SCREW_{i}_SMOOTH_SHANK_REFERENCE',bolt,(.64,.65,.66)),
                      (f'M3_WASHER_{i}_REFERENCE',washer,(.69,.70,.71)),
                      (f'M3_NUT_{i}_THREAD_OMITTED',nut,(.60,.62,.64))])
    return parts

def positioned_parts(ref,plate,shapes):
    parts=[('PLATE_80x85x10_NO_TAPPED_HOLES',plate,(.32,.61,.77)),
           ('GIMBAL_DIRECT_FIXED_HOLDER_RETAINED',ref,(.49,.57,.65)),
           ('2020_POST_ENVELOPE_ONLY',lib.box(-10,-64,-100,20,20,200),(.67,.69,.71))]
    bracket=lib.photo_bracket()
    for side,deg,x in [('LEFT',90,-10),('RIGHT',-90,10)]:
        t=lib.gp_Trsf();t.SetRotation(lib.gp_Ax1(lib.gp_Pnt(0,0,0),lib.gp_Dir(0,0,1)),math.radians(deg))
        t.SetTranslationPart(lib.gp_Vec(x,-54,0))
        parts.append((f'BRACKET_{side}_PHOTO_ENVELOPE_ASSUMED_HOLES',lib.transformed(bracket,t),(.68,.70,.72)))
    return parts+new_fasteners(shapes)

def preview(parts,shapes):
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',n)
    meshes=[(n,lib.mesh_faces(s),tuple(int(v*255) for v in c)) for n,s,c in parts]
    im=Image.new('RGB',(1800,1150),'white');dr=ImageDraw.Draw(im)
    dr.text((35,25),'R2 直接安装版 / 80×85×10 mm / 两角件 / 不攻丝',font=font(30),fill='black')
    prev.draw_panel(dr,meshes,(30,100,900,910),(1,1,.8),(-1,1,0))
    lower=[p for p in meshes if p[0]!='GIMBAL_DIRECT_FIXED_HOLDER_RETAINED']
    holder=('FIXED_HOLDER',lib.mesh_faces(shapes[18]),(170,180,190))
    prev.draw_panel(dr,lower+[holder],(965,120,760,765),(1,1,-1.05),(-1,1,0))
    dr.text((970,925),'仰视：四颗 M3 穿板，下方垫圈 + 螺母',font=font(24),fill='black')
    dr.text((35,1060),'取消两只大 U 形底座；保留舵机专用固定支架，支架底面直接贴合安装板。',font=font(23),fill='black')
    dr.text((35,1103),'相对 R1 降低 29 mm。角件、型材、替换螺钉为参考；未验证全角度运动及动态载荷。',font=font(21),fill='black')
    im.save(OUT/(NAME+'_assembly_preview.png'))
    # Interface close-up with plate/post excluded: actual fixed holder, new bolts.
    im=Image.new('RGB',(1500,1050),'white');dr=ImageDraw.Draw(im)
    dr.text((35,25),'直接安装接口：保留固定支架，取消其下方的大 U 底座',font=font(28),fill='black')
    close=[holder]+[p for p in meshes if p[0].startswith('M3')]
    prev.draw_panel(dr,close,(30,110,930,790),(.9,1,-.7),(-1,.9,0))
    for y,t in [(155,'四孔坐标（mm）：'),(202,'(0,-7)、(7,0)'),(246,'(0,7)、(-7,0)'),(333,'板上 4×φ3.4 通孔'),(379,'新板厚 10；支架底厚 2'),(425,'M3×16 从支架侧向下穿'),(471,'板下配薄垫圈与螺母'),(572,'先固定支架，再装回下舵机'),(618,'避免舵机挡住螺丝刀通道')]:
        dr.text((1000,y),t,font=font(24),fill='black')
    dr.text((35,970),'此图隐藏安装板以显示螺钉连接；正式装配中支架底面与板顶面直接贴合，不增加隔柱。',font=font(22),fill='black')
    im.save(OUT/(NAME+'_interface_preview.png'))

def verify_plate(plate):
    assert lib.BRepCheck_Analyzer(plate).IsValid()
    solids=lib.solid_list(plate);assert len(solids)==1
    bb=lib.bbox(plate);assert all(abs(a-b)<1e-6 for a,b in zip(bb,[-40,-69,0,40,16,10]))
    inside=lambda x,y,z:lib.BRepClass3d_SolidClassifier(solids[0],lib.gp_Pnt(x,y,z),1e-7).State()==lib.TopAbs_IN
    for x,y in MOUNT:
        for z in (.1,9.9):assert not inside(x,y,z) and inside(x+1.8,y,z)
    for x,y,axis in SLOTS:
        assert inside(x,y+4,4.4) and not inside(x,y+4,4.6)
        for sign in (-1,1):
            assert not inside(x+sign*8.9,y,.1) and inside(x+sign*9.1,y,.1)
            assert not inside(x+sign*10.9,y,9.9) and inside(x+sign*11.1,y,9.9)
    return dict(step_valid=True,plate_solid_count=1,plate_bbox_mm=bb,hole_coordinates_and_depths_verified=True)

def main():
    configure_exports();plate,blank=build_plate()
    area=80*85-(4-math.pi)*4-(22*26-2*(1-math.pi/4)*4)
    expected=area*10-4*math.pi*1.7**2*10-2*((6*12+math.pi*9)*10+((10-6)*12+math.pi*(25-9))*5.5)
    assert abs(lib.volume(plate)-expected)<1e-4
    file=OUT/(NAME+'_plate.step');lib.write_step(plate,file,NAME+'_NO_TAPPED_HOLES')
    qa=verify_plate(lib.read_step(file))
    ref,shapes,source=load_direct_reference()
    lib.write_step(ref,OUT/(NAME+'_gimbal_direct_reference.step'),'GIMBAL_WITH_FIXED_SERVO_HOLDER_NO_LARGE_BASES')
    parts=positioned_parts(ref,plate,shapes)
    collisions={}
    for (an,a,ac),(bn,b,bc) in itertools.combinations(parts,2):
        # Source servo subassembly is retained unchanged; check its interface to every new part.
        v=abs(lib.volume(lib.BRepAlgoAPI_Common(a,b).Shape()))
        collisions[an+'__'+bn]=v;assert v<1e-4,(an,bn,v)
    gap=prev.distance(ref,parts[2][1]);assert gap>3.9,gap
    head_clearance=min(prev.distance(s,shapes[27]) for n,s,c in parts if n.startswith('M3x16'))
    assert head_clearance>1,head_clearance
    assy=lib.assembly_step(parts)
    count=len(lib.solid_list(lib.read_step(assy)));assert count==51,count
    lib.export_2d(blank);preview(parts,shapes)
    mass=lib.volume(plate)*.0027
    qa.update(parameters_mm=P,source_modification=source,assembly_solid_count=count,
        aluminium_plate_mass_g=mass,R1_plate_mass_g=193.2207932456249,
        volume_mm3=lib.volume(plate),checked_new_part_pairs=len(collisions),
        maximum_collision_volume_mm3=max(collisions.values()),
        current_pose_gimbal_to_post_gap_mm=gap,new_screw_head_to_servo_gap_mm=head_clearance,
        fastener_reference=dict(screw='M3x16 pan head, source head geometry; thread omitted',
            count=4,washer_thickness=.5,nut_height=2.4,bolt_tip_z=-4,nut_bottom_z=-2.9,
            thread_protrusion_nominal_mm=1.1),
        bracket_hole_centres_assumed=True,full_motion_and_dynamic_load_validation=False)
    (OUT/(NAME+'_verification.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/(NAME+'_安装说明.md')).write_text(f'''# 015 云台 R2 直接安装版

取消两只大 U 形扩展底座；保留舵机专用金属固定支架（原 STEP 第 18 号实体，索引从 0 开始）。
舵机固定支架直接落在新板顶面；不是拆开舵机壳体，也不是把转动舵盘锁到底板。
相对 R1 云台降低 29 mm；所有保留零件仅整体平移，几何形状和相互位置未改变。

## 新板与接口
- 80×85×10 mm，6061-T6，不攻丝，板质量约 {mass:.1f} g。
- 新原点 O 为四颗下支架螺钉的孔组中心。R2 原点与 R1 不同，不能混用坐标。
- 四个 φ3.4 通孔：(0,-7)、(7,0)、(0,7)、(-7,0)。对应原固定支架 φ3 孔。
- 板边 X=±40；Y=-69、+16；立柱中心 (0,-54)。22×26 后开口避让立柱。
- 两角件仍在立柱左右侧；槽为 6×18 通槽，上沉槽 10×22、深 5.5。
- 图片仅确定角件 20×28×28、壁厚 3；孔中心距暂按 16，板槽允许 10～22 调整。
- 角件、T 螺母、筋条及工具空间仍需实物核对；T 螺母和 M5 连接五金未画入装配。

## 四颗直接安装螺钉
原螺钉夹持两层薄板，模型中头下长度约 8 mm；改为 10 mm 板后不能直接沿用该长度。
本版用四颗 M3×16 盘头螺钉从支架内侧向下穿，板下配 0.5 mm 薄平垫圈及约 2.4 mm 高六角螺母。
夹持厚度 10+2=12 mm；按上述垫圈和螺母，螺钉端部伸出约 1.1 mm。
螺钉头沿用原 CAD 的外形，头顶距舵机壳体约 {head_clearance:.2f} mm；购买件头高、垫圈厚度需核对。
普通厚螺母、厚垫圈或不同头型需重新选长度/检查空间。图中螺纹省略，不能以参考五金制造零件。

## 建议装配次序
1. 拆下两只大 U 底座及其连接五金，保留两轴驱动结构和下舵机固定支架。
2. 下舵机会遮住支架底部四个螺钉头的工具通道：暂时从金属支架拆下下舵机，不拆舵机壳体。
3. 先把平台与两个 2020 角件连接；再将保留的固定支架贴在板上，装四颗 M3×16 和板下薄垫圈、螺母。
4. 确认四颗螺钉头、端部与舵机无接触后，把下舵机装回原支架，恢复原来的舵机固定件。
5. 平台两侧通过匹配槽型的 T 形螺母固定。调高时托住整层，再松侧面连接点，调整后重新锁紧。

## 校核与文件
STEP 回读为单个有效板实体；尺寸、四孔位置、槽深均已检查。
当前姿态的新件与原云台之间无实体穿透；云台距立柱约 {gap:.2f} mm。
本次未验证整个运动范围、皮影杆和线缆包络或动态承载；试装后再确定舵机限位。
新板 STEP 用于加工；装配 STEP 为参考。DXF 是毫米 1:1，沉槽层不能切穿。
黑白 PDF 标注加工尺寸、公差、沉槽剖面。R0/R1 和厂家原始文件均已保留。
''',encoding='utf8')
    print(json.dumps(qa,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
