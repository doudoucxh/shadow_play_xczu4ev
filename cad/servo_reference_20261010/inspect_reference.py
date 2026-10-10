"""Read actual STEP geometry and render a proposed assembly reference, no hardware I/O."""
from pathlib import Path
import sys, math, json
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path[:0]=[r'D:\Desktop\张大头\tmp\ocp_deps',r'D:\Desktop\张大头\tmp\cad_deps',str(ROOT/'cad/gimbal_side_2020')]
import build_gimbal_platform as g
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from PIL import Image,ImageDraw,ImageFont

SOURCE=ROOT/'cad/gimbal_side_2020_direct/GIMBAL015_direct_2020_80x85x10_R2_gimbal_direct_reference.step'
parts=dict(zip([18]+list(range(27,61)),g.solid_list(g.read_step(SOURCE))))
assert len(parts)==35

def axis_of_round_horn(shape):
    choices=[]; exp=g.TopExp_Explorer(shape,g.TopAbs_FACE)
    while exp.More():
        surf=g.BRepAdaptor_Surface(g.TopoDS.Face_s(exp.Current()))
        if surf.GetType()==GeomAbs_Cylinder:
            c=surf.Cylinder();a=c.Axis();p=a.Location();d=a.Direction()
            choices.append((c.Radius(),(p.X(),p.Y(),p.Z()),(d.X(),d.Y(),d.Z())))
        exp.Next()
    return max(choices,key=lambda v:v[0])

yaw=axis_of_round_horn(parts[36]);pitch=axis_of_round_horn(parts[55])
assert abs(yaw[2][2])>.999 and abs(pitch[2][0])>.999
def dist(a,b):
    x=BRepExtrema_DistShapeShape(a,b);x.Perform();assert x.IsDone();return x.Value()

lower=g.compound([parts[18],parts[27]])
samples=[]
for angle in (0,90,135,160,180):
    t=g.gp_Trsf();t.SetRotation(g.gp_Ax1(g.gp_Pnt(*pitch[1]),g.gp_Dir(1,0,0)),math.radians(angle))
    upper=g.transformed(parts[56],t)
    common=g.BRepAlgoAPI_Common(upper,lower).Shape()
    samples.append({'relative_cad_pitch_degrees':angle,
                    'upper_U_to_lower_servo_and_holder_gap_mm':dist(upper,lower),
                    'intersection_volume_mm3':abs(g.volume(common))})
record={'source':str(SOURCE),'yaw_horn_axis':yaw,'pitch_horn_axis':pitch,
        'moving_U_source_solid':56,'lower_checked_source_solids':[18,27],
        'static_samples':samples,'not_servo_limits':True,
        'notes':'Angles are relative to CAD upright pose; no PWM mapping, cables, rods, post, neighbouring gimbals or motion path certification.'}
(OUT/'reference_inspection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')

palette={18:(106,125,144),27:(75,92,110),36:(61,128,185),37:(65,141,193),46:(93,112,135),55:(214,134,43),56:(239,155,54)}
meshes=[(str(i),g.mesh_faces(shape),palette.get(i,(153,164,175))) for i,shape in parts.items()]
plate=g.read_step(ROOT/'cad/gimbal_side_2020_direct/GIMBAL015_direct_2020_80x85x10_R2_plate.step')
meshes.append(('plate',g.mesh_faces(plate),(76,156,171)))

def panel(draw,rect,normal,right):
    n=g.Vec3(normal).normalize();u=g.Vec3(right).normalize();v=n.cross(u).normalize()
    points=[p for _,triangles,_ in meshes for triangle,_ in triangles for p in triangle]
    us=[p.dot(u) for p in points];vs=[p.dot(v) for p in points]
    lo,hi,bottom,top=min(us),max(us),min(vs),max(vs)
    x,y,w,h=rect;scale=min(w/(hi-lo),h/(top-bottom))
    ox=x+(w-(hi-lo)*scale)/2;oy=y+(h-(top-bottom)*scale)/2
    def project(point):
        p=g.Vec3(point);return (ox+(p.dot(u)-lo)*scale,oy+(top-p.dot(v))*scale)
    faces=[]
    light=(n+g.Vec3(-.2,.15,.1)).normalize()
    for _,triangles,color in meshes:
        for verts,no in triangles:
            if no.dot(n)<=1e-8:continue
            tone=.57+.43*max(0,no.dot(light))
            faces.append((sum(p.dot(n) for p in verts)/3,[project(p) for p in verts],tuple(int(c*tone) for c in color)))
    for _,polygon,color in sorted(faces,key=lambda row:row[0]):draw.polygon(polygon,fill=color)
    return project

font=lambda size:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
im=Image.new('RGB',(1600,1120),'#f7f9fc');d=ImageDraw.Draw(im)
d.text((44,25),'建议的装配参考姿态：上 U 框立起，顶部安装面水平',font=font(34),fill='#172d43')
d.text((44,80),'直接读取你的 STEP 模型；图中姿态尚未与实物 1500 μs 建立对应关系',font=font(23),fill='#546477')
proj=panel(d,(50,170,670,685),(1,1,.65),(-1,1,0))
side=panel(d,(970,245,505,505),(1,0,0),(0,1,0))
d.text((110,126),'立体视图',font=font(26),fill='#172d43')
d.text((1100,190),'沿俯仰轴看',font=font(26),fill='#172d43')

def leader(text,where,target,color):
    d.text(where,text,font=font(23),fill=color)
    bounds=d.textbbox(where,text,font=font(23));end=(where[0]+10,bounds[3]+8)
    d.line([end,target],fill=color,width=3);r=5
    d.ellipse((target[0]-r,target[1]-r,target[0]+r,target[1]+r),fill=color)

leader('橙色：俯仰 U 框', (595,170),proj((0,-20.4,126.4)),'#af6417')
leader('2 号：水平俯仰轴',(575,450),proj((28,-20.4,76.37)),'#af6417')
axis_start=proj((yaw[1][0],yaw[1][1],18));axis_end=proj((yaw[1][0],yaw[1][1],78))
for k in range(0,16,2):
    a=tuple(axis_start[j]+(axis_end[j]-axis_start[j])*k/16 for j in (0,1))
    b=tuple(axis_start[j]+(axis_end[j]-axis_start[j])*(k+1)/16 for j in (0,1))
    d.line([a,b],fill='#286496',width=3)
leader('1 号：竖直偏航轴',(650,680),proj((yaw[1][0],yaw[1][1],45)),'#286496')
top_left=side((-25,-32.9,128.37));top_right=side((-25,-7.9,128.37))
d.line([(top_left[0]-24,top_left[1]-16),(top_right[0]+24,top_right[1]-16)],fill='#c88025',width=3)
d.text((1020,760),'顶部面 ∥ 安装板',font=font(24),fill='#172d43')
d.text((945,806),'U 框处在俯仰轴上方，不向下折叠',font=font(23),fill='#172d43')
d.rounded_rectangle((38,895,1562,1082),radius=15,fill='#e7edf5')
for y,text in [(915,'① 先在解除支架约束的状态下，让舵机到 1500 μs。'),
               (958,'② 断电后保持输出轴参考位置，调整舵盘与 U 框的安装角度，使其接近上图。'),
               (1001,'③ 再检查小范围活动余量；图中“参考姿态”不等于已验证全行程。')]:
    d.text((62,y),text,font=font(25),fill='#213a55')
d.text((48,1090),'编号仅对应已确认的 1/2 号这一组；其余组方向需逐组确认。',font=font(18),fill='#5c6e80')
im.save(OUT/'gimbal_reference_pose.png')
print(json.dumps(record,ensure_ascii=False))
