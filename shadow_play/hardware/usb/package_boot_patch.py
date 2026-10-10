"""Package bootgen's candidate as a compact, integrity-checked FSBL delta."""
import argparse
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from usb_boot_candidate import partitions, sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bootgen-image', type=Path, required=True)
    p.add_argument('--source-manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    data = args.bootgen_image.read_bytes()
    parts = partitions(data)
    template = bytearray(data)
    for part in parts[1:]:
        template[part['offset']:part['offset']+part['length']] = bytes(part['length'])
    source = json.loads(args.source_manifest.read_text())
    manifest = dict(source_sha256=source['sha256'],
                    source_partition_sha256=source['partition_sha256'],
                    template_sha256=sha(template),
                    new_fsbl_pmu_sha256=parts[0]['sha256'],
                    format='zynqmp-fsbl-delta-v1', validated_on_hardware=False)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'template.bin.gz').write_bytes(gzip.compress(bytes(template), mtime=0))
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
