"""Verify and stage a swapped-UART delta bundle on SD; no hardware access."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

BASE=Path('/run/media/mmcblk0p2/piying/rail-uart-query-20261019/servo10_dual_uart.bit.bin')
BASE_SHA='ea680d88d2d149157490ebbe27b253b3814d6d2df17aeebb477047bb4bc81e90'


def sha(data):return hashlib.sha256(data).hexdigest()


def apply_delta(before, compressed, delta):
    if (delta['base_sha256']!=BASE_SHA or sha(before)!=BASE_SHA or
            len(before)!=delta['bytes']):
        raise ValueError('Source image content mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as zipped:
        difference=zipped.read(len(before)+1)
    if len(difference)!=len(before):raise ValueError('Delta size mismatch')
    after=bytes(a^b for a,b in zip(before,difference))
    if sha(after)!=delta['target_sha256']:raise ValueError('Reconstructed image mismatch')
    return after


def checked_members(tar):
    members=tar.getmembers()
    names=[m.name for m in members]
    if len(names)!=len(set(names)) or sum(m.size for m in members)>16000000:
        raise ValueError('Duplicate or oversize archive')
    for m in members:
        name=PurePosixPath(m.name)
        if not m.isfile() or name.is_absolute() or '..' in name.parts or '\\' in m.name:
            raise ValueError('Unsafe member')
    return members


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--archive-sha',required=True)
    p.add_argument('--stage',type=Path,required=True)
    args=p.parse_args()
    raw=args.archive.read_bytes()
    if sha(raw)!=args.archive_sha:raise ValueError('Archive hash mismatch')
    if (args.stage.parent.resolve()!=Path('/run/media/mmcblk0p2/piying') or
            not args.stage.name.startswith('uart-swap-query-20261019')):
        raise ValueError('Expected independent SD staging path')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        members=checked_members(tar)
        args.stage.mkdir(exist_ok=False)
        for m in members:
            target=args.stage.joinpath(*PurePosixPath(m.name).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:output.write(tar.extractfile(m).read())
    delta=json.loads((args.stage/'DELTA.json').read_text())
    if (delta['base_sha256']!=BASE_SHA or delta['base_path']!=str(BASE) or
            delta['target_name']!='servo10_uart_swapped.bit.bin'):
        raise ValueError('Unexpected delta identity')
    before=BASE.read_bytes()
    after=apply_delta(before,(args.stage/'image.xor.gz').read_bytes(),delta)
    with (args.stage/delta['target_name']).open('xb') as output:output.write(after)
    manifest=json.loads((args.stage/'MANIFEST.json').read_text())
    actual={str(p.relative_to(args.stage)) for p in args.stage.rglob('*') if p.is_file()}
    if actual!=set(manifest['files'])|{'MANIFEST.json'}:raise ValueError('Staged member set mismatch')
    for name,expected in manifest['files'].items():
        target=(args.stage/name).resolve()
        if not target.is_relative_to(args.stage.resolve()) or sha(target.read_bytes())!=expected:
            raise ValueError('Staged hash mismatch: '+name)
        if target.suffix=='.py':compile(target.read_text(),str(target),'exec')
    print('SWAPPED_UART_STAGE_VERIFIED '+json.dumps(dict(stage=str(args.stage),files=len(actual),
        image_sha=delta['target_sha256'],hardware_access=False,motor_packets_sent=False)))


if __name__=='__main__':main()
