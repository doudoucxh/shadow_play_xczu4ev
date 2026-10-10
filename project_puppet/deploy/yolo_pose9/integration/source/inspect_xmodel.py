import argparse
import json
from pathlib import Path
import xir

p=argparse.ArgumentParser()
p.add_argument('model', type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
g=xir.Graph.deserialize(str(a.model))
rows=[]
for s in g.get_root_subgraph().toposort_child_subgraph():
    rows.append({'name':s.get_name(),'device':s.get_attr('device') if s.has_attr('device') else None,
                 'inputs':[{'name':t.name,'shape':t.dims} for t in s.get_input_tensors()],
                 'outputs':[{'name':t.name,'shape':t.dims} for t in s.get_output_tensors()],
                 'fingerprint':str(s.get_attr('dpu_fingerprint')) if s.has_attr('dpu_fingerprint') else None})
result={'subgraphs':rows,'dpu_count':sum(r['device']=='DPU' for r in rows)}
cpu=[r for r in rows if r['device']=='CPU']
result['cpu_boundary_count']=len(cpu)
result['cpu_boundaries_are_shape_preserving']=all(
    len(r['inputs'])==len(r['outputs'])==1 and r['inputs'][0]['shape']==r['outputs'][0]['shape']
    for r in cpu)
a.output.write_text(json.dumps(result,indent=2))
assert result['dpu_count']==1,result
assert result['cpu_boundaries_are_shape_preserving'], 'Found computational CPU fallback in CNN'
print(json.dumps(result,indent=2))
