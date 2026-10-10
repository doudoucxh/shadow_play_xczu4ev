import json,sys
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parent/'source'))
from raw_model import RawPose
root=Path(sys.argv[1])
model=RawPose(json.loads((root/'model/raw_architecture.json').read_text())).eval()
with np.load(root/'model/raw_weights.npz') as state:
    model.load_state_dict({k:torch.from_numpy(state[k].copy()) for k in state.files})
torch.set_num_threads(1)
macs=[0]
def hook(module,inputs,out):
    macs[0]+=out.numel()*(module.in_channels//module.groups)*module.kernel_size[0]*module.kernel_size[1]
for mod in model.modules():
    if isinstance(mod,torch.nn.Conv2d): mod.register_forward_hook(hook)
with torch.no_grad(): out=model(torch.zeros(1,3,384,384))
print(json.dumps({'input':[1,3,384,384],'parameters':sum(p.numel() for p in model.parameters()),
                  'conv_macs':macs[0],'conv_gflops_2_per_mac':2*macs[0]/1e9,
                  'convention':'Conv multiply/add only; excludes BN/ReLU/pool and A53 postprocessing',
                  'outputs':[list(t.shape) for t in out]},indent=2))
