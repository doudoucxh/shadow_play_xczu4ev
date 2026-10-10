"""Build an inactive USB FSBL candidate, preserving the board's other partitions.

No boot activation, device writes, reboot, or motor operation. BOOT.BIN is read
only; the output must be a new file. A reviewed bootgen template supplies all
headers, padding and the new FSBL/old PMUFW combined partition.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct


def sha(data):
    return hashlib.sha256(data).hexdigest()


def partitions(data):
    if len(data) < 0xA0 or data[0x20:0x28] != bytes.fromhex('665599aa584e4c58'):
        raise ValueError('Not a ZynqMP bootgen image')
    if sum(struct.unpack_from('<11I', data, 0x20)) & 0xFFFFFFFF != 0xFFFFFFFF:
        raise ValueError('Invalid boot header checksum')
    offset = struct.unpack_from('<I', data, 0x9C)[0]
    result, visited = [], set()
    while offset:
        if offset in visited or offset + 64 > len(data):
            raise ValueError('Invalid partition header chain')
        visited.add(offset)
        w = struct.unpack_from('<16I', data, offset)
        if sum(w) & 0xFFFFFFFF != 0xFFFFFFFF:
            raise ValueError('Invalid partition header checksum')
        start, size = w[8] * 4, w[2] * 4
        if not size or start + size > len(data):
            raise ValueError('Partition outside boot image')
        if result and start < result[-1]['offset'] + result[-1]['length']:
            raise ValueError('Overlapping partitions')
        result.append(dict(offset=start, length=size, load=w[6] | (w[7] << 32),
                           execute=w[4] | (w[5] << 32),
                           attributes=w[9], sha256=sha(data[start:start + size])))
        offset = w[3] * 4
    if len(result) != 5:
        raise ValueError('Expected FSBL/PMU, PL, BL31, DTB, U-Boot layout')
    return result


def make_candidate(source, template, manifest):
    if manifest.get('format') != 'zynqmp-fsbl-delta-v1':
        raise ValueError('Unsupported patch format')
    if sha(source) != manifest['source_sha256']:
        raise ValueError('Source BOOT.BIN changed; refusing to patch')
    if sha(template) != manifest['template_sha256']:
        raise ValueError('Patch template hash mismatch')
    old, new = partitions(source), partitions(template)
    for key in ('load', 'execute', 'attributes'):
        if old[0][key] != new[0][key]:
            raise ValueError('FSBL execution metadata changed')
    if [p['sha256'] for p in old] != manifest['source_partition_sha256']:
        raise ValueError('Unexpected source partitions')
    # BootROM loads the PMU image before the FSBL from the combined partition.
    old_pmu = struct.unpack_from('<I', source, 0x38)[0]
    new_pmu = struct.unpack_from('<I', template, 0x38)[0]
    if old_pmu != new_pmu:
        raise ValueError('PMU firmware size changed')
    a, b = old[0]['offset'], new[0]['offset']
    if source[a:a + old_pmu] != template[b:b + new_pmu]:
        raise ValueError('PMU firmware changed')
    out = bytearray(template)
    for index in range(1, 5):
        p, q = old[index], new[index]
        for key in ('length', 'load', 'execute', 'attributes'):
            if p[key] != q[key]:
                raise ValueError('Unrelated partition metadata changed: '+str(index))
        start, end = q['offset'], q['offset'] + q['length']
        if any(template[start:end]):
            raise ValueError('Expected an empty preserved-partition slot')
        out[start:end] = source[p['offset']:p['offset'] + p['length']]
    result = bytes(out)
    info = partitions(result)
    if info[0]['sha256'] != manifest['new_fsbl_pmu_sha256']:
        raise ValueError('New FSBL verification failed')
    if [p['sha256'] for p in info[1:]] != [p['sha256'] for p in old[1:]]:
        raise ValueError('An original partition was altered')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--patch-dir', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or args.output.resolve() == args.source.resolve():
        raise ValueError('Output must be a new, inactive candidate file')
    manifest = json.loads((args.patch_dir/'manifest.json').read_text())
    template = gzip.decompress((args.patch_dir/'template.bin.gz').read_bytes())
    result = make_candidate(args.source.read_bytes(), template, manifest)
    with args.output.open('xb') as stream:
        stream.write(result)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    if sha(args.output.read_bytes()) != sha(result):
        raise IOError('Candidate read-back verification failed')
    print(json.dumps({'candidate':str(args.output),'sha256':sha(result),
                      'bytes':len(result),'activated':False,
                      'preserved_partitions':['PMUFW','PL','BL31','DTB','U-Boot']}))


if __name__ == '__main__':
    main()
