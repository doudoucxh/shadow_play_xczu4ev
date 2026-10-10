"""R2: 10 mm adapter without tapped holes; exact STEP and faceted 3D DXF."""
from pathlib import Path
import sys, os, math, json, zipfile
from collections import Counter
from itertools import product
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'tmp'/'cad_deps'))
sys.path.insert(0,str(ROOT/'tmp'/'ocp_deps'))
import build_adapter_10mm as base
import ezdxf
from ezdxf.render import MeshVertexMerger, MeshTransformer
from ezdxf.acis import api as acis
from ezdxf.acis import sat
from ezdxf.math import Vec3
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopAbs import TopAbs_REVERSED
from OCP.GeomAbs import GeomAbs_Cone
from PIL import Image, ImageDraw, ImageFont

NAME='SGX_2020_adapter_60x60x10_R2_notap'

def indexed_sat_records(entities,version):
    # Same record order and pointer semantics as ezdxf's SAT writer, with an
    # identity index replacing its repeated linear scans for large meshes.
    indices={id(entity):i for i,entity in enumerate(entities)}
    def ptr(entity):
        if entity is sat.NULL_PTR:return '$-1'
        return '$'+str(indices[id(entity)])
    for entity in entities:
        tokens=[entity.name,ptr(entity.attributes)]
        if version>=700:tokens.append(str(entity.id))
        tokens.extend(ptr(v) if isinstance(v,sat.SatEntity) else str(v) for v in entity.data)
        tokens.append('#')
        yield ' '.join(tokens)

def read(path):
    prev=Path.cwd();os.chdir(OUT)
    try:return base.read_step(path)
    finally:os.chdir(prev)

def make_shape():
    shape=read(OUT/'SGX_2020_adapter_60x60x10_R1.step')
    for x,y in base.B:
        shape=base.BRepAlgoAPI_Cut(shape,base.cylinder(x,y,-1,2.75,12)).Shape()
        cone=BRepPrimAPI_MakeCone(base.gp_Ax2(base.gp_Pnt(x,y,0),base.gp_Dir(0,0,1)),5.75,2.75,3).Shape()
        shape=base.BRepAlgoAPI_Cut(shape,cone).Shape()
    unify=base.ShapeUpgrade_UnifySameDomain(shape,True,True,False);unify.Build()
    shape=unify.Shape()
    assert base.BRepCheck_Analyzer(shape).IsValid()
    return shape

def mesh_shape(shape):
    tess=BRepMesh_IncrementalMesh(shape,.005,False,.10,False)
    tess.Perform();assert tess.IsDone()
    mesh=MeshVertexMerger(precision=6)
    ex=base.TopExp_Explorer(shape,base.TopAbs_FACE)
    while ex.More():
        face=base.TopoDS.Face_s(ex.Current())
        loc=TopLoc_Location();tri=BRep_Tool.Triangulation_s(face,loc)
        assert tri is not None
        transform=loc.Transformation()
        for i in range(1,tri.NbTriangles()+1):
            ids=list(tri.Triangle(i).Get())
            if face.Orientation()==TopAbs_REVERSED:ids[1],ids[2]=ids[2],ids[1]
            pts=[]
            for j in ids:
                p=tri.Node(j).Transformed(transform);pts.append((p.X(),p.Y(),p.Z()))
            mesh.add_face(pts)
        ex.Next()
    mesh=MeshTransformer.from_builder(mesh).optimize_vertices(6)
    d=mesh.diagnose()
    assert d.is_closed_surface and d.is_manifold and not d.is_edge_balance_broken
    assert d.volume()>0
    assert d.euler_characteristic==-14, d.euler_characteristic  # one body, eight through holes
    return mesh

def export_dxf(mesh,kind):
    doc=ezdxf.new('R2010');doc.units=4
    doc.header['$MEASUREMENT']=1
    doc.header['$INSBASE']=(0.,0.,0.)
    doc.layers.new('PLATE_3D',dxfattribs={'color':8,'true_color':0xA0B1BC})
    if kind=='3dsolid':
        body=acis.body_from_mesh(mesh)
        e=doc.modelspace().add_3dsolid(dxfattribs={'layer':'PLATE_3D'})
        original_writer=sat.build_str_records
        original_double=sat.SatDataExporter.write_double
        try:
            sat.build_str_records=indexed_sat_records
            # Default :g retains only six significant digits. Preserve mesh
            # coordinates and face normals through the text SAT encoding.
            sat.SatDataExporter.write_double=lambda self,value:self.data.append(format(value,'.17g'))
            acis.export_dxf(e,[body])
        finally:
            sat.build_str_records=original_writer
            sat.SatDataExporter.write_double=original_double
    else:mesh.render_mesh(doc.modelspace(),dxfattribs={'layer':'PLATE_3D'})
    doc.set_modelspace_vport(95,center=(0,0))
    vp=doc.viewports.get('*Active')[0]
    vp.dxf.direction=(1,-1,1.2);vp.dxf.target=(0,0,5);vp.dxf.render_mode=4
    vp.dxf.ucs_icon=1
    path=OUT/(NAME+'_'+kind+'.dxf');doc.saveas(path)
    re=ezdxf.readfile(path);audit=re.audit();assert not audit.errors
    assert re.units==4
    assert len(re.modelspace())==1
    if kind=='3dsolid':
        e=list(re.modelspace().query('3DSOLID'))[0]
        bodies=acis.load_dxf(e);assert len(bodies)==1
        meshes=acis.mesh_from_body(bodies[0]);assert len(meshes)==1
        back=meshes[0].optimize_vertices(6)
    else:
        back=MeshTransformer.from_mesh(list(re.modelspace().query('MESH'))[0]).optimize_vertices(6)
    d=back.diagnose()
    assert d.is_closed_surface and d.is_manifold and not d.is_edge_balance_broken
    # SAT stores decimal coordinates; its rounding can accumulate in volume.
    # Check coordinate preservation as well as a tight relative volume bound.
    # Vertex order may change on readback. Match spatially without depending
    # on lexicographic ordering of nearly equal floating-point coordinates.
    assert len(mesh.vertices)==len(back.vertices)
    bucket_size=1e-4
    key=lambda v:tuple(math.floor(c/bucket_size) for c in v)
    buckets={}
    for i,v in enumerate(mesh.vertices):buckets.setdefault(key(v),[]).append(i)
    matched=set();max_coordinate_error=0.
    for v in back.vertices:
        k=key(v);candidates=[]
        for offset in product((-1,0,1),repeat=3):
            candidates.extend(buckets.get(tuple(a+b for a,b in zip(k,offset)),[]))
        assert candidates
        distance,index=min((math.dist(v,mesh.vertices[i]),i) for i in candidates)
        assert index not in matched
        matched.add(index);max_coordinate_error=max(max_coordinate_error,distance)
    assert max_coordinate_error<1e-5,max_coordinate_error
    source_volume=mesh.diagnose().volume()
    volume_error=abs(d.volume()-source_volume)
    assert volume_error<max(.002,abs(source_volume)*1e-7),volume_error
    dims=d.bbox.size
    assert all(abs(a-b)<1e-4 for a,b in zip(dims,(60,60,10))),dims
    return path,{'entity_type':'3DSOLID' if kind=='3dsolid' else 'MESH','audit_errors':0,
                 'closed_surface':True,'manifold':True,'bbox_mm':list(dims),'volume_mm3':d.volume(),
                 'roundtrip_max_coordinate_error_mm':max_coordinate_error,
                 'roundtrip_volume_error_mm3':volume_error}

def preview(mesh):
    # Technical orthographic preview made from the same closed surface as the DXF.
    scale=2
    im=Image.new('RGB',(1500*scale,780*scale),(249,250,252));dr=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',n*scale)
    def text(pos,txt,n=22,col=(35,48,62)):dr.text((pos[0]*scale,pos[1]*scale),txt,font=font(n),fill=col)
    text((44,24),'60 × 60 × 10 mm 转接板 / R2 不攻丝版',29)
    text((44,68),'两幅图显示同一零件；沉孔朝向不同，安装时勿翻反。',19,(90,105,120))
    for side,cx in [(1,385),(-1,1110)]:
        n=Vec3(1,-1,1.35*side).normalize()
        right=Vec3(1,1,0).normalize();up=n.cross(right).normalize()
        def project(v):
            p=v-Vec3(0,0,5)
            return ((cx+p.dot(right)*7.0)*scale,(382-p.dot(up)*7.0)*scale)
        polys=[]
        for face in mesh.faces:
            vs=[mesh.vertices[i] for i in face]
            normal=(vs[1]-vs[0]).cross(vs[2]-vs[0]).normalize()
            if normal.dot(n)<=1e-8:continue
            z=sum(v.dot(n) for v in vs)/3
            brightness=.62+.33*max(0,normal.dot(Vec3(-.35,-.55,.76*side).normalize()))
            rgb=tuple(int(v*brightness) for v in (186,204,216))
            polys.append((z,[project(v) for v in vs],rgb))
        for _,pts,rgb in sorted(polys,key=lambda a:a[0]):dr.polygon(pts,fill=rgb)
        # Keep the shaded surface: drawing all crease edges here would show
        # hidden rims on the opposite face and obscure countersink direction.
        if side==1:
            text((215,637),'上面：4 个 M4 圆柱沉孔',23)
            text((205,675),'另 4 个为 M5 螺栓通孔 φ5.5',20,(80,99,112))
        else:
            text((935,637),'下面：4 个 M5 锥形沉孔',23)
            text((910,675),'φ11.5 × 90°，螺栓头不应凸出板底',20,(80,99,112))
    text((44,739),'底板无螺纹；M5 螺母在角码上方。滑块仍需原有 M4 安装螺纹。',20)
    im=im.resize((1500,780),Image.Resampling.LANCZOS)
    path=OUT/(NAME+'_preview.png');im.save(path)
    return path

def main():
    shape=make_shape()
    base.Interface_Static.SetCVal_s('write.step.schema','AP214IS')
    base.Interface_Static.SetCVal_s('write.step.unit','MM')
    base.Interface_Static.SetCVal_s('write.step.product.name',NAME+'__NO_TAPPED_HOLES')
    writer=base.STEPControl_Writer();writer.Transfer(shape,base.STEPControl_AsIs)
    step=OUT/(NAME+'.step');prev=Path.cwd();os.chdir(OUT)
    try:assert writer.Write(step.name)==base.IFSelect_RetDone
    finally:os.chdir(prev)
    shape=read(step);assert base.BRepCheck_Analyzer(shape).IsValid()
    ex=base.TopExp_Explorer(shape,base.TopAbs_SOLID);solids=[]
    while ex.More():solids.append(base.TopoDS.Solid_s(ex.Current()));ex.Next()
    assert len(solids)==1
    def is_in(x,y,z):return base.BRepClass3d_SolidClassifier(solids[0],base.gp_Pnt(x,y,z),1e-7).State()==base.TopAbs_IN
    for x,y in base.B:
        assert not is_in(x,y,9.9)
        assert not is_in(x+4,y,.2)
        assert is_in(x+4,y,2.0)
        assert is_in(x+3,y,3.2)
    for x,y in base.A:
        assert not is_in(x,y,.1)
        assert is_in(x+3,y,5.4) and not is_in(x+3,y,5.6)
    g=base.GProp_GProps();base.BRepGProp.VolumeProperties_s(shape,g)
    b=(60*60-(4-math.pi)*4)*10
    a=4*math.pi*(2.25**2*10+(4**2-2.25**2)*4.5)
    holes=4*math.pi*2.75**2*10
    csk=4*(math.pi*3/3*(5.75**2+5.75*2.75+2.75**2)-math.pi*2.75**2*3)
    assert abs(g.Mass()-(b-a-holes-csk))<1e-4
    mesh=mesh_shape(shape);d=mesh.diagnose()
    assert abs(d.volume()-g.Mass())/g.Mass()<.0005
    solid_dxf,solid_report=export_dxf(mesh,'3dsolid')
    mesh_dxf,mesh_report=export_dxf(mesh,'mesh')
    png=preview(mesh)
    report={'revision':'R2','dimensions_mm':[60,60,10],'all_plate_holes_untapped':True,
            'exact_step_valid':True,'exact_step_solid_count':1,'mass_g_at_2_70':g.Mass()*.0027,
            'm4_top_counterbore_depth':4.5,'m5_through_diameter':5.5,
            'm5_bottom_countersink':{'diameter':11.5,'included_angle_degrees':90,'depth':3},
            'dxf_geometry':'faceted closed solid; cylinders and cones are approximated',
            'meshing_linear_deflection_mm':.005,'triangle_count':len(mesh.faces),
            'relative_volume_difference':abs(d.volume()-g.Mass())/g.Mass(),
            'dxf_solid_readback':solid_report,'dxf_mesh_readback':mesh_report}
    qa=OUT/(NAME+'_verification.json');qa.write_text(json.dumps(report,indent=2),encoding='utf8')
    note=OUT/(NAME+'_加工与安装说明.md')
    note.write_text(f'''# R2 不攻丝转接板 / 60×60×10 mm

本版用于 SGX 滑块连接 2020 立柱；底板所有孔均为光孔，无需攻丝。
材料建议 6061-T6，四角 R2，约 {g.Mass()*.0027:.1f} g（仅板）。

## 三维文件
- *_3dsolid.dxf：DXF R2010，毫米，单个 ACIS 3DSOLID 分面实体，可三维旋转。
- *_mesh.dxf：相同形状的 MESH 网格兼容版，供不支持 ACIS 的查看器使用。
- *.step：保留精确圆柱孔和圆锥沉孔的 STEP 实体，推荐用于加工和修改。
- DXF 曲面经过分面近似，不是解析圆柱/圆锥，也没有特征历史；不能把它误当作二维切割图。
- 已做文件回读及闭合性检查，尚未在用户实际 CAD 软件中验证兼容性。

## 孔加工
坐标原点为板中心，底面 Z=0，顶面 Z=10。
- 外侧 A 孔：(±15,±15)，4×φ4.5 通孔，上面 φ8 圆柱沉孔深 4.5。
- 轴线上 B 孔：(0,±20)、(±20,0)，4×φ5.5 通孔，下面 φ11.5×90° 锥形沉孔（理论深 3）。
- 不攻任何螺纹！不要按旧 R0/R1 的 M5 攻丝要求加工。
- M5 使用 90° 沉头螺栓，试配确认头部平于或略低于底面，不得凸起。
- 外形/厚度 ±0.10；孔中心 ±0.05；A/B 通孔直径 +0.15/0。
- A 沉孔直径 +0.20/0、深度 +0.20/0；B 沉孔大径 +0.20/0，角度 90°±0.5°。
- 去毛刺，外缘轻倒钝；沉头承压面不要额外大倒角；两装配面平面度各 0.10。

## 安装顺序和螺母空间
1. 将四颗 M5 沉头螺栓从板底向上穿过 B 孔。
2. 将平底开口 L 角码套在上方，角码上面加平垫圈和 M5 螺母。
   选可放入螺母和扳手的角码；有窄加强筋的角码可能无法操作，不能只按“2020角码”购买。
3. 在板还没有装到滑块上时，完成角码与立柱的试装、找正和紧固。
4. 再用四颗 M4 圆柱头螺钉从 A 孔上方将整件固定到滑块。
   四个 M4 安装位置位于立柱角部外侧，需要保留内六角扳手通道。

此方案不在滑块与板之间放螺母，板底保持平整。
角码仍须符合：底孔距型材贴合面 10 mm，底脚外伸≤20 mm，宽≤20 mm，底面无凸齿。
M5 沉头螺栓公称长度包含头部，应覆盖板厚、角码、垫圈和螺母，完整啮合并露出 1～2 牙。
M4 螺钉伸入滑块约 L-5.5 mm，具体长度按实物有效孔深选择。
滑块本身仍依赖原有 M4 螺纹；如果实物滑块也是光孔，这一版本不能直接固定。
实物型号、M4 孔深和动态载荷尚未核定；底部/角码配合需要实物检查。

## 规格与格式参考
- 沉头螺栓规格参考（90°，不同标准/厂商头径须核对）：
  https://www.accu.co.uk/countersunk-socket-head-screws/5469-SSK-M5-25-A2
- DXF 分面 ACIS 导出机制： https://ezdxf.readthedocs.io/en/stable/acis.html
''',encoding='utf8')
    pack=OUT/(NAME+'_3D图纸包.zip')
    with zipfile.ZipFile(pack,'w',zipfile.ZIP_DEFLATED) as z:
        for p in (solid_dxf,mesh_dxf,step,note,qa,png,Path(__file__)):z.write(p,p.name)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
