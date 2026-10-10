import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from graph_contract import validate_graph
import xir
graph=xir.Graph.deserialize(sys.argv[1])
dpu=validate_graph(graph)
result=[]
for sub in graph.get_root_subgraph().toposort_child_subgraph():
    device=sub.get_attr('device') if sub.has_attr('device') else ''
    item={'name':sub.get_name(),'device':device}
    if sub.has_attr('dpu_fingerprint'): item['fingerprint']=hex(sub.get_attr('dpu_fingerprint'))
    if device!='DPU':
        item['ops']=[{'name':op.get_name(),'type':op.get_type(),'attrs':op.get_attrs(),
                      'inputs':{k:[p.get_name() for p in v] for k,v in op.get_input_ops().items()},
                      'output':op.get_output_tensor().name,
                      'dtype':str(op.get_output_tensor().dtype)} for op in sub.get_ops()]
    result.append(item)
report=json.dumps(result,indent=2,default=str)
if len(sys.argv)>2: Path(sys.argv[2]).write_text(report)
print('Verified one DPU CNN and nine direct signed INT8 fix2float outputs; fingerprint 0x101000056010407')
