"""Three identical no-tap shelves staggered left/front/right in the top 100 mm."""
from pathlib import Path
import sys,math,itertools,json
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'output/cad/gimbal_side_2020_direct'))
import build_direct_platform as r2
lib=r2.lib
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.GeomAbs import GeomAbs_Line
from PIL import Image,ImageDraw,ImageFont

NAME='GIMBAL015_three_top100_80x115x10_R3'
MOUNT=r2.MOUNT
SLOTS=[(-26.,-84.,'X'),(26.,-84.,'X')]
OUTLINE_VERTICES=[(-40,-99),(40,-99),(40,-74),(22,-45),(22,16),(-22,16),(-22,-45),(-40,-74)]
LAYERS=[dict(label='LEFT_LOW',cn='左 / 低',angle=-90,z=-72,color=(.31,.57,.76)),
        dict(label='CENTRE_MID',cn='中 / 中',angle=0,z=-41,color=(.49,.68,.54)),
        dict(label='RIGHT_HIGH',cn='右 / 高',angle=90,z=-10,color=(.76,.58,.37))]
P=dict(width=80,length=115,thickness=10,x_bounds=[-40,40],y_bounds=[-99,16],
       outer_vertices_before_filleting=OUTLINE_VERTICES,all_outline_corner_radii=2,
       front_width=44,rear_straight_length=25,taper_y_bounds=[-74,-45],
       notch_width=26,notch_depth=38,notch_front_y=-61,notch_inner_radius=2,
       post_center=[0,-84],post_to_gimbal_hole_pattern_centre=84,
       gimbal_holes=MOUNT,gimbal_hole_diameter=3.4,slots=SLOTS,
       slot_through=[6,18],slot_top_pocket=[10,22,5.5],plate_quantity=3,brackets_per_plate=2,
       column_example_length=200,top_datum_z=0,installation_region_z=[-100,0],
       plate_top_offsets_below_column_top=[62,31,0],layer_pitch=31,
       layers=LAYERS,layout_basis='front view from +Y toward origin; screen right is -X; centre platform extends +Y')

def configure_exports():
    lib.OUT=OUT;lib.NAME=NAME;lib.MOUNT=MOUNT;lib.SLOTS=SLOTS

def rounded_blank():
    p=lib.BRepBuilderAPI_MakePolygon()
    for x,y in OUTLINE_VERTICES:p.Add(lib.gp_Pnt(x,y,0))
    p.Close();face=lib.BRepBuilderAPI_MakeFace(p.Wire()).Face()
    raw=lib.BRepPrimAPI_MakePrism(face,lib.gp_Vec(0,0,10)).Shape()
    fillet=BRepFilletAPI_MakeFillet(raw);e=lib.TopExp_Explorer(raw,lib.TopAbs_EDGE);count=0
    while e.More():
        edge=lib.TopoDS.Edge_s(e.Current());c=lib.BRepAdaptor_Curve(edge)
        a,b=c.Value(c.FirstParameter()),c.Value(c.LastParameter())
        if c.GetType()==GeomAbs_Line and abs(a.Z()-b.Z())>9.99:
            fillet.Add(2.,edge);count+=1
        e.Next()
    # Each prism edge is visited twice when exploring face ownership in OCCT.
    fillet.Build();assert fillet.IsDone();s=fillet.Shape()
    n=lib.fuse(lib.box(-13,-100,-1,26,37,12),lib.box(-11,-63,-1,22,2,12))
    for x in (-11,11):n=lib.fuse(n,lib.cyl(x,-63,-1,2,12))
    return lib.unify(lib.cut(s,n))

def build_plate():
    blank=rounded_blank();plate=blank
    for x,y in MOUNT:plate=lib.cut(plate,lib.cyl(x,y,-1,1.7,12))
    for x,y,axis in SLOTS:
        plate=lib.cut(plate,lib.capsule(x,y,axis,6,-1,12))
        plate=lib.cut(plate,lib.capsule(x,y,axis,10,4.5,6.5))
    return lib.unify(plate),blank

def local_parts(plate,ref,shapes):
    parts=[('PLATE_80x115x10_QTY3',plate,(.36,.62,.77)),
           ('GIMBAL_FIXED_HOLDER_DIRECT_MOUNT',ref,(.50,.57,.64))]
    bracket=lib.photo_bracket()
    for side,deg,x in [('LEFT',90,-10),('RIGHT',-90,10)]:
        t=lib.gp_Trsf();t.SetRotation(lib.gp_Ax1(lib.gp_Pnt(0,0,0),lib.gp_Dir(0,0,1)),math.radians(deg))
        t.SetTranslationPart(lib.gp_Vec(x,-84,0))
        parts.append((f'BRACKET_{side}_PHOTO_REFERENCE',lib.transformed(bracket,t),(.66,.68,.70)))
    return parts+r2.new_fasteners(shapes)

def placement(layer):
    a=math.radians(layer['angle']);c,s=math.cos(a),math.sin(a)
    t=lib.gp_Trsf();t.SetValues(c,-s,0,-84*s,s,c,0,84*c,0,0,1,layer['z'])
    return t

def fastener_envelopes():
    """Conservative external M5 envelopes, used for adjacent-layer clearance only."""
    result=[]
    for x in (-26,26):
        # Below horizontal foot: washer/nut plus exposed screw tip.
        result.append((f'M5_UNDER_FOOT_{x}',lib.cyl(x,-84,-12,5,9)))
    for side in (-1,1):
        # Vertical bracket wall ends 13 mm from post centre. Diameter 10 x 7 outward.
        result.append((f'M5_SIDE_HEAD_{side}',lib.cyl(side*13,-84,-16,5,7,(side,0,0))))
    return result

def bbox_overlap(a,b,tol=1e-7):
    return all(min(a[k+3],b[k+3])-max(a[k],b[k])>tol for k in range(3))

def verify_plate(plate):
    assert lib.BRepCheck_Analyzer(plate).IsValid()
    solids=lib.solid_list(plate);assert len(solids)==1
    bb=lib.bbox(plate);assert all(abs(a-b)<1e-6 for a,b in zip(bb,[-40,-99,0,40,16,10]))
    inside=lambda x,y,z:lib.BRepClass3d_SolidClassifier(solids[0],lib.gp_Pnt(x,y,z),1e-7).State()==lib.TopAbs_IN
    for x,y in MOUNT:
        for z in (.1,9.9):assert not inside(x,y,z) and inside(x+1.8,y,z)
    for x,y,_ in SLOTS:
        assert inside(x,y+4,4.4) and not inside(x,y+4,4.6)
        assert not inside(x+8.9,y,.1) and inside(x+9.1,y,.1)
        assert not inside(x+10.9,y,9.9) and inside(x+11.1,y,9.9)
    assert not inside(0,-61.1,5) and inside(0,-60.9,5)
    assert not inside(23,0,5) and inside(21,0,5)
    return dict(valid=True,solid_count=1,bbox_mm=bb,hole_and_slot_and_notch_checks=True)

def previews(parts,groups):
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',n)
    cache=[(n,lib.mesh_faces(s),tuple(int(v*255) for v in c)) for n,s,c in parts]
    im=Image.new('RGB',(2000,1330),'white');dr=ImageDraw.Draw(im)
    dr.text((35,25),'R3 三平台布置 / 左低、中间居中、右高 / 固定区位于型材顶部 100 mm',font=font(29),fill='black')
    r2.prev.draw_panel(dr,cache,(35,115,1100,1010),(1,1,.65),(-1,1,0))
    r2.prev.draw_panel(dr,cache,(1170,115,785,850),(0,1,0),(-1,0,0))
    dr.text((1410,995),'正视图：左 -62 / 中 -31 / 右 0',font=font(24),fill='black')
    for i,t in enumerate(['标高为平台上表面相对型材顶端的距离（mm）。',
                           '三块同款板：80×115×10，前端收窄为 44；每层两个角件。',
                           '云台向外移至距柱心 84；避让口加深为 38，防止上层角件撞下层板。',
                           '当前姿态已检查；未验证完整转动范围、杆件、线缆及动态承载。']):
        dr.text((35,1160+i*37),t,font=font(23),fill='black')
    im.save(OUT/(NAME+'_assembly_preview.png'))
    im=Image.new('RGB',(1600,1200),'white');dr=ImageDraw.Draw(im)
    dr.text((35,25),'俯视布置 / 中间平台向前，左右平台分别向两侧',font=font(28),fill='black')
    # Show shelves and fittings without servos so the overlap/relief is visible.
    small=[v for v in cache if 'GIMBAL' not in v[0] and not v[0].startswith('M3')]
    r2.prev.draw_panel(dr,small,(70,110,1120,950),(0,0,1),(-1,0,0))
    for i,t in enumerate(['左层：上表面 -62','中层：上表面 -31','右层：上表面 0','顶端安装区：-100～0','角件共 6 个','各层通过 T 螺母锁紧']):
        dr.text((1230,250+65*i),t,font=font(24),fill='black')
    dr.text((35,1130),'两侧平台需绕立柱转向；不是把三套云台垂直叠在同一个位置。',font=font(24),fill='black')
    im.save(OUT/(NAME+'_top_layout.png'))

def main():
    configure_exports();plate,blank=build_plate()
    lib.write_step(plate,OUT/(NAME+'_plate_QTY3.step'),'COMMON_PLATE_NO_TAPPED_HOLES_QTY3')
    qa=verify_plate(lib.read_step(OUT/(NAME+'_plate_QTY3.step')))
    ref,shapes,source=r2.load_direct_reference();base=local_parts(plate,ref,shapes)
    groups=[];parts=[('2020_POST_200MM_ENVELOPE_TOP_Z0',lib.box(-10,-10,-200,20,20,200),(.69,.71,.73))]
    env_groups=[]
    for layer in LAYERS:
        tr=placement(layer);items=[]
        for n,s,c in base:
            col=layer['color'] if n.startswith('PLATE') else c
            items.append((layer['label']+'__'+n,lib.transformed(s,tr),col))
        groups.append(items);parts+=items
        env_groups.append([(layer['label']+'__'+n,lib.transformed(s,tr)) for n,s in fastener_envelopes()])
    cached=[(n,s,lib.bbox(s)) for n,s,c in parts];checked=0;max_v=0
    for (an,a,ba),(bn,b,bb) in itertools.combinations(cached,2):
        if not bbox_overlap(ba,bb):continue
        v=abs(lib.volume(lib.BRepAlgoAPI_Common(a,b).Shape()));checked+=1;max_v=max(max_v,v)
        assert v<1e-4,(an,bn,v)
    clearances={}
    for i,j in [(0,1),(0,2),(1,2)]:
        pair=f'{LAYERS[i]["label"]}__{LAYERS[j]["label"]}'
        a=lib.compound([s for n,s,c in groups[i]]);b=lib.compound([s for n,s,c in groups[j]])
        gap=r2.prev.distance(a,b);assert gap>2.0,(pair,gap)
        clearances[pair]=gap
    env_checks=0;env_candidates=0
    for i,envs in enumerate(env_groups):
        for ename,e in envs:
            eb=lib.bbox(e)
            for j,group in enumerate(groups):
                if i==j:continue
                for n,s,c in group:
                    env_candidates+=1
                    if bbox_overlap(eb,lib.bbox(s)):
                        v=abs(lib.volume(lib.BRepAlgoAPI_Common(e,s).Shape()));env_checks+=1
                        assert v<1e-4,(ename,n,'external M5 envelope',v)
    region=[]
    for layer,group in zip(LAYERS,groups):
        localregion=lib.bbox(lib.compound([s for n,s,c in group if 'PLATE' in n or 'BRACKET' in n]))
        assert localregion[2]>=-100-1e-6 and localregion[5]<=1e-6
        region.append(dict(layer=layer['label'],z_extent=[localregion[2],localregion[5]],
                           plate_top_z=layer['z']+10,side_fastener_axis_z=layer['z']-16))
    lib.export_2d(blank);assy=lib.assembly_step(parts)
    reread=lib.read_step(assy);count=len(lib.solid_list(reread));assert count==151,count
    previews(parts,groups)
    mass=lib.volume(plate)*.0027
    qa.update(parameters_mm=P,source=source['source'],plate_mass_g=mass,total_plate_mass_g=mass*3,
        assembly_solids=count,assembly_bbox_mm=lib.bbox(reread),checked_actual_shape_pairs=checked,
        maximum_collision_volume_mm3=max_v,inter_layer_minimum_distances_mm=clearances,
        M5_external_envelope_pairs_tested=env_candidates,M5_external_envelope_boolean_checks=env_checks,
        M5_envelopes='diameter 10; side-head outward 7; lower fitting reaches 12 below plate',
        installation_regions=region,plate_upper_faces_measured_from_post_top_mm=[-62,-31,0],
        top_zone_fulfilled=True,column_is_envelope_only=True,brackets_are_photo_approximations=True,
        full_motion_dynamic_load_and_cables_verified=False)
    (OUT/(NAME+'_verification.json')).write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
    note=f'''# R3 顶部 100 mm 三层平台

## 布置
按从正面看左低、中间居中、右高布置。中间平台向前，左右平台向两侧，各转 90°。
型材顶端定义 Z=0，向下为负；示意 2020 立柱长 200，底端 Z=-200。
左 / 中 / 右平台上表面 Z=-62 / -31 / 0，相邻层间距 31 mm。
三层的板和角件合计占据 Z=-100～0，符合顶部 100 mm 安装区；云台可高出顶端。
各层角件的立柱连接螺钉中心暂按 Z=-88 / -57 / -26。此值依赖角件实际孔距。
最高云台在当前姿态超出立柱顶端约 118.37 mm；不要把安装区理解为整个云台包络高度。

## 修改
三块同款板均为 80×115×10 mm，前端收窄到 44 mm；每块约 {mass:.1f} g，三块合计 {mass*3:.1f} g。
原点仍为四颗支架安装螺钉孔组中心；孔为 (0,-7)、(7,0)、(0,7)、(-7,0)，φ3.4 通孔，不攻丝。
立柱中心改为 P=(0,-84)，把云台向外移 30 mm，避免下层云台碰上层板和角件。
后部开口宽 26、深 38；比 R2 加宽 4、加深 12，给上层横向角件留出空间。
后部宽 80 保留两角件连接，前部收窄减重。外轮廓转折及开口内角均 R2。
角件仍采用图片中 20×28×28、壁厚约 3 的型号；每层 2 个，总共 6 个。
单层占一对相对的槽面；三层转向后合计使用立柱四个槽面。左右两层在相同槽面相隔 62 mm。

## 安装
所有尺寸按毫米。先在型材上标出顶端下 62、31、0 的平台上表面位置。
角件上承托面比各板上表面低 10。角件竖直边朝下，两个水平边朝立柱两侧伸出。
先装左层，再装中层，最后装右层；支架先固定到板上，然后装回下舵机。
每套云台仍用四颗 M3×16 从固定支架侧向下穿板，板下配薄垫圈和螺母，核对头高/长度。
每层两颗 M5 连接板与角件，两颗 M5 配适合实际 2020 槽型的 T 螺母连接立柱。
T 螺母和 M5 五金未作为制造模型绘出；用保守外包络检查其对其他层的避让。
由于三层紧凑，不能任意滑动其中一层：托住整层，调整后检查相邻层间隙并锁紧。

## 校核范围
三块板、六角件、三套原云台和 M3 五金在当前姿态无实体穿透。
各层之间最近距离（当前姿态）：{json.dumps(clearances,ensure_ascii=False)} mm。
检查了额外 M5 头部/螺母外包络与其他层没有穿透；包络未代替实物规格。
角件孔距按照片参考假定 16，仍需实测孔位、筋条和工具空间。
尚未验证全角度运动、皮影杆、线缆、总重量或动态载荷；实际运动限位需另行确定。

## 文件用途
- plate_QTY3.step：同一种加工板，数量 3。
- assembly_reference.step：三平台总装；200 mm 立柱、角件、五金为参考模型。
- 2D_1to1.dxf：单位毫米，轮廓/通孔/上沉槽分层，不能把沉槽切穿。
- PDF：黑白单板尺寸与三层安装标高图，R3。
保留厂家模型及 R0～R2，不混用不同版本孔位。
'''
    (OUT/(NAME+'_三层安装说明.md')).write_text(note,encoding='utf8')
    print(json.dumps(qa,ensure_ascii=True,indent=2),flush=True)

if __name__=='__main__':main()
