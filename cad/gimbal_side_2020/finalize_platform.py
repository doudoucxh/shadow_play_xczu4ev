from pathlib import Path
import json,zipfile
import build_gimbal_platform as m

plate=m.read_step(m.OUT/(m.NAME+'_plate.step'))
solid=m.solid_list(plate)[0]
inside=lambda x,y,z:m.BRepClass3d_SolidClassifier(solid,m.gp_Pnt(x,y,z),1e-7).State()==m.TopAbs_IN
for x,y in m.MOUNT:
    for z in (.1,9.9):assert not inside(x,y,z) and inside(x+1.8,y,z)
for x,y,axis in m.SLOTS:
    u=(1,0) if axis=='X' else (0,1);v=(-u[1],u[0])
    assert inside(x+4*v[0],y+4*v[1],4.4)
    assert not inside(x+4*v[0],y+4*v[1],4.6)
    for sign in (-1,1):
        assert not inside(x+sign*8.9*u[0],y+sign*8.9*u[1],.1)
        assert inside(x+sign*9.1*u[0],y+sign*9.1*u[1],.1)
        assert not inside(x+sign*10.9*u[0],y+sign*10.9*u[1],9.9)
        assert inside(x+sign*11.1*u[0],y+sign*11.1*u[1],9.9)
assembly=m.read_step(m.OUT/(m.NAME+'_assembly_reference.step'))
count=len(m.solid_list(assembly));assert count==66,count
qa_path=m.OUT/(m.NAME+'_verification.json')
qa=json.loads(qa_path.read_text(encoding='utf8'))
qa['exported_assembly_solid_count']=count
qa['exported_plate_holes_slots_and_pocket_depth_point_checked']=True
qa_path.write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
pdf=m.ROOT/'output'/'pdf'/(m.NAME+'_engineering_A3.pdf')
paths=[m.OUT/(m.NAME+s) for s in ('_plate.step','_assembly_reference.step','_2D_1to1.dxf',
       '_assembly_preview.png','_安装说明.md','_verification.json')]+[pdf]
pack=m.OUT/(m.NAME+'_图纸包.zip')
with zipfile.ZipFile(pack,'w',zipfile.ZIP_DEFLATED) as z:
    for p in paths:assert p.is_file();z.write(p,p.name)
with zipfile.ZipFile(pack) as z:assert z.testzip() is None
print(json.dumps({'assembly_solids':count,'plate_geometry_readback_verified':True,
                  'package':str(pack),'files':[{ 'name':p.name,'bytes':p.stat().st_size} for p in paths]},ensure_ascii=True,indent=2))
