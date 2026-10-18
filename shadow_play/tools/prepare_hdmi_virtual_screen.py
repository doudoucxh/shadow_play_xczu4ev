"""Build private Xvfb dependencies from official Debian archives; print the installer SHA256.

Run from the repository root. No board commands or system package changes.
"""
import concurrent.futures,hashlib,io,json,lzma,tarfile,urllib.request
from pathlib import Path
folder=Path('.board_work/ui-browser-20261017')
folder.mkdir(parents=True, exist_ok=True)
index=folder/'bullseye-arm64-Packages.xz'
if not index.exists():index.write_bytes(urllib.request.urlopen('https://archive.debian.org/debian/dists/bullseye/main/binary-arm64/Packages.xz',timeout=60).read())
names=set('libselinux1 libgcrypt20 libaudit1 libcap-ng0 libbsd0 libmd0 libxfont2 libfontenc1 libgpg-error0 libpcre2-8-0 x11-xkb-utils xkb-data libxkbfile1'.split())
rows={}
for paragraph in lzma.decompress(index.read_bytes()).decode().split('\n\n'):
 row=dict(line.split(': ',1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
 if row.get('Package') in names:rows[row['Package']]=row
assert set(rows)==names
def download(row):
 url='https://archive.debian.org/debian/'+row['Filename'];p=folder/Path(row['Filename']).name
 if not p.exists():p.write_bytes(urllib.request.urlopen(url,timeout=60).read())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['SHA256']
 return dict(name=row['Package'],url=url,sha256=row['SHA256'],path=str(p))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:packages=list(pool.map(download,rows.values()))
p=folder/'xvfb_1.20.11-1+deb11u18_arm64.deb'
xvfb_url='https://archive.debian.org/debian-security/pool/updates/main/x/xorg-server/'+p.name
xvfb_sha='81a22aa0ecd62ed03158a4a64eb2b9f30cf292b4220f33adf6f7df32eed67b2e'
if not p.exists():p.write_bytes(urllib.request.urlopen(xvfb_url,timeout=60).read())
if hashlib.sha256(p.read_bytes()).hexdigest()!=xvfb_sha:
 raise ValueError('Xvfb package checksum mismatch')
packages.append(dict(name='xvfb',url=xvfb_url,sha256=xvfb_sha,path=str(p)))
files={};links={}
for package in packages:
 b=Path(package['path']).read_bytes();i=8
 while i+60<=len(b):
  header=b[i:i+60];length=int(header[48:58]);i+=60
  if header[:16].decode().strip().startswith('data.tar'):
   with tarfile.open(fileobj=io.BytesIO(b[i:i+length])) as archive:
    for entry in archive:
     name=entry.name.removeprefix('./')
     if entry.isfile():files[name]=archive.extractfile(entry).read()
     elif entry.issym():links[name]=entry.linkname
  i+=length+length%2
result={}
for name,data in files.items():
 if '/aarch64-linux-gnu/' in name and '.so.' in name:result['lib/'+Path(name).name]=data
 elif name in ('usr/bin/Xvfb','usr/bin/xkbcomp'):result['bin/'+Path(name).name]=data
 elif name.startswith('usr/share/X11/xkb/'):result[name[4:]]=data
 elif name.endswith('/copyright'):result['licenses/'+name.split('/')[-2]+'-copyright']=data
for name,target in links.items():
 if '/aarch64-linux-gnu/' in name and '.so.' in name:
  resolved=(Path(name).parent/target).as_posix() if not target.startswith('/') else target[1:]
  if resolved in files:result['lib/'+Path(name).name]=files[resolved]
manifest=dict(packages=packages,files={name:hashlib.sha256(data).hexdigest() for name,data in result.items()})
result['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
out=folder/'xvfb-private-20261017.tar.gz'
with tarfile.open(out,'w:gz') as archive:
 for name,data in sorted(result.items()):
  item=tarfile.TarInfo('xvfb-private-20261017/'+name);item.size=len(data);item.mode=0o755 if name.startswith('bin/') else 0o644;archive.addfile(item,io.BytesIO(data))
print(json.dumps(dict(bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),files=len(result),packages=len(packages))),flush=True)
