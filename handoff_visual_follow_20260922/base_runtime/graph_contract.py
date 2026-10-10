"""Fail closed unless the compiled graph consists of one audited CNN plus dequantizers."""
EXPECTED_FINGERPRINT = 0x101000056010407

def validate_graph(graph):
    children = graph.get_root_subgraph().toposort_child_subgraph()
    groups = {}
    for sub in children:
        device = sub.get_attr('device').upper() if sub.has_attr('device') else ''
        groups.setdefault(device, []).append(sub)
    if set(groups) != {'USER','DPU','CPU'} or len(groups['DPU']) != 1 or len(groups['CPU']) != 9:
        raise ValueError('Expected USER input, one DPU CNN and nine fix2float boundaries')
    dpu = groups['DPU'][0]
    attr = 'dpu_fingerprint' if dpu.has_attr('dpu_fingerprint') else 'fingerprint'
    if not dpu.has_attr(attr) or int(dpu.get_attr(attr)) != EXPECTED_FINGERPRINT:
        raise ValueError('Compiled DPU fingerprint does not match approved B4096 target')
    outputs = {t.name:t for t in dpu.get_output_tensors()}
    covered = set()
    for sub in groups['CPU']:
        ops = list(sub.get_ops())
        ins, outs = list(sub.get_input_tensors()), list(sub.get_output_tensors())
        if len(ops)!=1 or ops[0].get_type()!='fix2float' or len(ins)!=1 or len(outs)!=1:
            raise ValueError('Unapproved CPU computation: '+sub.get_name())
        op = ops[0]
        predecessors = [p for values in op.get_input_ops().values() for p in values]
        if len(predecessors)!=1 or predecessors[0].get_output_tensor().name!=ins[0].name:
            raise ValueError('Unexpected dequantizer input connection')
        name = ins[0].name
        if name not in outputs or name in covered or tuple(ins[0].dims)!=tuple(outs[0].dims):
            raise ValueError('CPU boundary is not a unique direct DPU output')
        t = outputs[name]
        if str(t.dtype).lower() not in ('xint8','int8') or str(outs[0].dtype).lower()!='float32':
            raise ValueError('Unexpected boundary dtype')
        if not t.has_attr('fix_point') or op.get_attr('fix_point')!=t.get_attr('fix_point'):
            raise ValueError('Boundary quantization scale mismatch')
        if op.get_attr('bit_width')!=8 or not op.get_attr('if_signed'):
            raise ValueError('Expected signed INT8 dequantization')
        covered.add(name)
    if covered != set(outputs): raise ValueError('Uncovered DPU output')
    for sub in groups['USER']:
        if any(op.get_type()!='data-fix' or op.get_input_ops() for op in sub.get_ops()):
            raise ValueError('Unexpected USER input computation')
    return dpu
