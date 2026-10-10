import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
original=json.loads((root/'incoming/manifest.json').read_text(encoding='utf-8'))
for name,entry in original['files'].items():
    data=(root/'incoming'/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==entry['sha256'],name
for name in ('BOOT.BIN','boot.scr','image.ub'):
    assert (root/'sd_candidate'/name).is_file(),name
files={}
for folder in ('model','training','runtime','evaluation','integration','rollback'):
    for path in sorted((root/folder).rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts: continue
        data=path.read_bytes()
        files[path.relative_to(root).as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
for name in ('BOOT.BIN','boot.scr','image.ub','system.bit'):
    path=root/'sd_candidate'/name; data=path.read_bytes()
    files[path.relative_to(root).as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
report={'release':'yolov8n-pose9-relu-v1-b4096-integrated',
        'status':'offline-verified; board acceptance pending',
        'source_manifest':'incoming/manifest.json','files':files}
(root/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for name,item in files.items(): assert hashlib.sha256((root/name).read_bytes()).hexdigest()==item['sha256']
print('Verified upstream 22 files and integrated manifest',len(files),'files')
