"""Add a YOLO service to a known-good CPIO image; preserve old runtime for rollback."""
import gzip,json,hashlib,stat,sys,time
from pathlib import Path
base,release,output=map(Path,sys.argv[1:])
data=gzip.decompress(base.read_bytes())
entries={}; position=0
while position+110<=len(data):
    start=position; header=data[start:start+110]
    assert header[:6]==b'070701'
    fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
    end=start+110+fields[11]; name=data[start+110:end-1].decode()
    if name.startswith('./'): name=name[2:]
    body=(end+3)&~3; position=(body+fields[6]+3)&~3
    if name=='TRAILER!!!': break
    assert name not in entries
    entries[name]=(data[start:position],data[body:body+fields[6]])
else: raise ValueError('Missing trailer')
def record(name,content,mode,ino):
    encoded=name.encode()+b'\0'; fields=[ino,mode,0,0,1,int(time.time()),len(content),0,0,0,0,len(encoded),0]
    header=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+encoded
    return header+b'\0'*((-len(header))%4)+content+b'\0'*((-len(content))%4)
new={}
for name in ['opt/shadow/yolo_pose9','opt/shadow/yolo_pose9/runtime','opt/shadow/yolo_pose9/model']:
    new[name]=(b'',stat.S_IFDIR|0o755)
for name in ['runtime.py','postprocess.py','graph_contract.py']:
    new['opt/shadow/yolo_pose9/runtime/'+name]=((release/'runtime'/name).read_bytes(),stat.S_IFREG|0o644)
new['opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel']=((release/'model/yolo_pose9_b4096.xmodel').read_bytes(),stat.S_IFREG|0o644)
for source,target in [('shadow-yolo-pose','usr/bin/shadow-yolo-pose'),('rollback-arm-chain.sh','usr/bin/shadow-rollback-arm-chain')]:
    new[target]=((release/'integration'/source).read_bytes(),stat.S_IFREG|0o755)
new['lib/systemd/system/shadow-yolo-pose.service']=((release/'integration/shadow-yolo-pose.service').read_bytes(),stat.S_IFREG|0o644)
new['etc/systemd/system/multi-user.target.wants/shadow-yolo-pose.service']=(b'../../../../lib/systemd/system/shadow-yolo-pose.service',stat.S_IFLNK|0o777)
disabled='etc/systemd/system/multi-user.target.wants/shadow-arm-chain.service'
assert disabled in entries
assert 'usr/bin/shadow-hw-init' in entries
chunks=[raw for name,(raw,_) in entries.items() if name!=disabled and name not in new]
for i,(name,(body,mode)) in enumerate(new.items(),0x100000): chunks.append(record(name,body,mode,i))
chunks.append(record('TRAILER!!!',b'',0,0))
archive=b''.join(chunks); archive+=b'\0'*((-len(archive))%512)
output.write_bytes(gzip.compress(archive,compresslevel=9,mtime=0))
print(json.dumps({'added':list(new),'disabled_autostart':disabled,
                  'old_runtime_retained':True,'rootfs_sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))
