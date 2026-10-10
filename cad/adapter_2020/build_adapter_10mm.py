"""Build the R1 60 x 60 x 10 mm adapter and verify the exported STEP.

R0 geometry and documents remain available under their original filenames.
M5 threads are represented by tap-drill cylinders; see the accompanying notes.
"""
from pathlib import Path
import sys, math, json, os

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tmp' / 'ocp_deps'))

from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_IN, TopAbs_OUT
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

NAME = 'SGX_2020_adapter_60x60x10_R1'
P = {'width':60., 'length':60., 'thickness':10., 'corner_radius':2.,
     'clearance_diameter':4.5, 'counterbore_diameter':8., 'counterbore_depth':4.5,
     'tap_drill_diameter':4.2, 'thread':'M5x0.8-6H THRU'}
A = [(-15.,-15.), (15.,-15.), (15.,15.), (-15.,15.)]
B = [(0.,20.), (20.,0.), (0.,-20.), (-20.,0.)]

def cylinder(x, y, z, r, h):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(0,0,1)),r,h).Shape()

def read_step(path):
    reader = STEPControl_Reader()
    assert reader.ReadFile(path.name) == IFSelect_RetDone
    assert reader.TransferRoots() > 0
    return reader.OneShape()

def cylinder_features(shape):
    features = set()
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        surf = BRepAdaptor_Surface(TopoDS.Face_s(ex.Current()))
        if surf.GetType() == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            axis = cyl.Axis()
            if abs(axis.Direction().Z()) > .99999:
                p = axis.Location()
                features.add((round(p.X(),6),round(p.Y(),6),round(cyl.Radius(),6)))
        ex.Next()
    return features

def main():
    w,l,t,r = (P[k] for k in ('width','length','thickness','corner_radius'))
    floor = t - P['counterbore_depth']
    shape = BRepPrimAPI_MakeBox(gp_Pnt(-w/2+r,-l/2,0), w-2*r,l,t).Shape()
    shape = BRepAlgoAPI_Fuse(shape, BRepPrimAPI_MakeBox(gp_Pnt(-w/2,-l/2+r,0),w,l-2*r,t).Shape()).Shape()
    for x in (-w/2+r,w/2-r):
        for y in (-l/2+r,l/2-r):
            shape = BRepAlgoAPI_Fuse(shape,cylinder(x,y,0,r,t)).Shape()
    for x,y in A:
        shape = BRepAlgoAPI_Cut(shape,cylinder(x,y,-1,P['clearance_diameter']/2,t+2)).Shape()
        shape = BRepAlgoAPI_Cut(shape,cylinder(x,y,floor,P['counterbore_diameter']/2,P['counterbore_depth']+1)).Shape()
    for x,y in B:
        shape = BRepAlgoAPI_Cut(shape,cylinder(x,y,-1,P['tap_drill_diameter']/2,t+2)).Shape()
    unify = ShapeUpgrade_UnifySameDomain(shape,True,True,False)
    unify.Build()
    shape = unify.Shape()
    assert BRepCheck_Analyzer(shape).IsValid()

    Interface_Static.SetCVal_s('write.step.schema','AP214IS')
    Interface_Static.SetCVal_s('write.step.unit','MM')
    Interface_Static.SetCVal_s('write.step.product.name',NAME+'__B_HOLES_TAP_M5x0.8')
    writer = STEPControl_Writer()
    writer.Transfer(shape,STEPControl_AsIs)
    path = OUT/(NAME+'.step')
    previous = Path.cwd()
    os.chdir(OUT)
    try:
        assert writer.Write(path.name) == IFSelect_RetDone
        result = read_step(path)
        original = read_step(OUT/'SGX_2020_adapter_60x60x8_R0.step')
    finally:
        os.chdir(previous)
    assert BRepCheck_Analyzer(result).IsValid()
    box = Bnd_Box(); BRepBndLib.Add_s(result,box)
    bb = box.Get()
    extents = [bb[i+3]-bb[i] for i in range(3)]
    assert all(abs(a-b)<1e-5 for a,b in zip(extents,[w,l,t])),extents
    g = GProp_GProps(); BRepGProp.VolumeProperties_s(result,g)
    expected = (w*l-(4-math.pi)*r*r)*t
    expected -= len(A)*math.pi*((P['clearance_diameter']/2)**2*t +
        ((P['counterbore_diameter']/2)**2-(P['clearance_diameter']/2)**2)*P['counterbore_depth'])
    expected -= len(B)*math.pi*(P['tap_drill_diameter']/2)**2*t
    assert abs(g.Mass()-expected)<1e-4
    solids=[]
    ex=TopExp_Explorer(result,TopAbs_SOLID)
    while ex.More():solids.append(TopoDS.Solid_s(ex.Current()));ex.Next()
    assert len(solids)==1
    # Geometry-derived verification that all XY locations/radii match R0.
    actual_features=cylinder_features(result)
    assert actual_features == cylinder_features(original)
    expected_features={(x,y,2.25) for x,y in A}|{(x,y,4.) for x,y in A}|{(x,y,2.1) for x,y in B}
    assert expected_features <= actual_features
    solid=solids[0]
    def inside(x,y,z):
        return BRepClass3d_SolidClassifier(solid,gp_Pnt(x,y,z),1e-7).State()==TopAbs_IN
    for x,y in A:
        assert not inside(x,y,.5) and not inside(x,y,t-.5)
        assert inside(x+3,y,floor-.1)  # shoulder has material below 5.5 mm
        assert not inside(x+3,y,floor+.1)  # counterbore above 5.5 mm
    for x,y in B:
        assert not inside(x,y,.5) and not inside(x,y,t-.5)
    assert inside(0,0,.1) and inside(0,0,t-.1)
    report={
        'revision':'R1', 'date':'2026-09-27', 'parameters_mm':P,
        'valid_step_readback':True, 'solid_count':len(solids), 'bbox_mm':extents,
        'volume_mm3':g.Mass(), 'estimated_mass_g_at_2_70':g.Mass()*.0027,
        'hole_centres_and_radii_match_R0':True,
        'verified_counterbore_floor_z_mm':floor,
        'slide_hole_centres_mm':A, 'M5_tapped_hole_centres_mm':B,
        'thread_representation':'4.2 mm tap-drill geometry, tap M5x0.8-6H THRU after drilling',
        'assembly_limitations':'Slide M4 threads and usable hole depth remain unconfirmed. No dynamic load rating assigned.'
    }
    (OUT/(NAME+'_verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    notes=f'''# SGX 滑块 - 2020 立柱转接板 R1 / 10 mm

本版按用户要求将原 R0 厚度 8 mm 改为 10 mm，外形与孔位不变。
STEP 文件是毫米单位、单个闭合三维实体；板中心 X=Y=0，底面 Z=0，顶面 Z=10。
材料建议：6061-T6 铝合金。模型估算重量 {g.Mass()*.0027:.1f} g，不含螺钉和角码。

## 几何与加工
- 外形 60×60×10 mm，四角 R2；去毛刺小倒钝不建模。
- A1～A4：中心 (±15,±15)，4×φ4.5 通孔；上面 φ8 圆柱沉孔，深 4.5。
- B1～B4：中心 (0,±20)、(±20,0)，4×M5×0.8-6H 通螺纹。
- M5 孔在 STEP 中以 φ4.2 底孔表示，无螺旋牙型；交加工方时须带上这份说明。
- 沉孔下面的剩余厚度从 3.5 改为 5.5 mm。
- 外形及厚度 ±0.10 mm；孔中心坐标 ±0.05 mm。
- A 孔 φ4.5 +0.15/0；沉孔 φ8 +0.20/0，深 4.5 +0.20/0。
- 两装配面各自平面度 0.10 mm，上下平行度 0.10 mm。

## 螺钉与装配变化
M4 螺钉伸入滑块的长度约为 L - 5.5 mm（不加垫片）。
例如 M4×12 伸入约 6.5 mm，等同旧 8 mm 板配 M4×10 的伸入量。
仅在实物有效螺纹深度允许时使用；不能顶到孔底或内部机构。
M5 角码螺钉并非必须加长：3 mm 厚角码配 M5×10，仍约啮合 7 mm。
角码底面须平整，底孔中心距型材贴合面 10 mm，配 2020 型材。

## 状态
已通过 STEP 回读、单实体有效性、60×60×10 外形、体积、孔位与沉孔深度检查。
滑块实物的 M4 四孔、30×30 孔距和有效孔深仍须核对；未核定动态载荷。
旧文件名含 60x60x8_R0 的图纸属于旧厚度版本，不能作为本版厚度/螺钉长度依据。
'''
    (OUT/(NAME+'_加工与装配说明.md')).write_text(notes,encoding='utf8')
    print(json.dumps(report,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
