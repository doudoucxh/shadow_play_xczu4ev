"""Package the separately checked four-pin UART ECO as a data-only XOR delta."""
import argparse
import copy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import tarfile

from load_rail_query_candidate import BASE_SHA, digest
from load_swapped_uart_candidate import STANDARD_SHA, verify_swapped
from package_rail_uart_candidate import io_ports, save
from zdt_uartlite_telemetry import SWAPPED_PORTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--build-log',type=Path,required=True)
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    log=args.build_log.read_text(encoding='utf-8')
    for token in ('SERVO_IMAGE_DESIGN_CHECKS_PASS','RAIL_UART_SWAPPED_DESIGN_CHECKS_PASS','RAIL_UART_SWAPPED_BITSTREAM_READY'):
        if token not in log.splitlines():raise ValueError('Incomplete build: '+token)
    standard=root/'shadow_play/hardware/rail_uart/release'
    base=standard/'servo10_dual_uart.bit.bin'
    if digest(base)!=STANDARD_SHA:raise ValueError('Unexpected source image')
    old=io_ports(root/'.review_work/rail_uart_20261019/verified_io.rpt')
    new=io_ports(args.build/'verified_io.rpt')
    changed={'person_uart_tx','person_uart_rx','tiger_uart_tx','tiger_uart_rx'}
    if set(new)!=set(old) or any(new[k]!=old[k] for k in old if k not in changed):
        raise ValueError('Unrelated I/O changed')
    for name,info in SWAPPED_PORTS.items():
        for suffix,direction in [('tx','OUTPUT'),('rx','INPUT')]:
            if new[name+'_uart_'+suffix]!=(info[suffix+'_pin'],direction,'LVCMOS33'):
                raise ValueError('Swapped I/O mismatch')
    rows=[line.split('|') for line in (args.build/'verified_io.rpt').read_text().splitlines()]
    for name in ('person_uart_tx','tiger_uart_tx'):
        found=[r for r in rows if len(r)>8 and r[2].strip()==name]
        if len(found)!=1 or found[0][8].strip()!='4':raise ValueError('TX strength is not 4')
    lines=(args.build/'verified_timing.rpt').read_text().splitlines()
    index=next(i for i,line in enumerate(lines) if 'WNS(ns)' in line and 'WPWS(ns)' in line)
    timing=lines[index+2].split()
    wns,whs,wpws=(float(timing[i]) for i in (0,4,8))
    if min(wns,whs,wpws)<0 or any(int(timing[i]) for i in (2,6,10)):
        raise ValueError('Failing timing endpoints')
    image=args.build/'servo10_uart_swapped.bit.bin'
    m=copy.deepcopy(json.loads((standard/'servo10_dual_uart.manifest.json').read_text()))
    m.update(sha256=digest(image),previous_sha256=STANDARD_SHA,wns_ns=wns,whs_ns=whs,wpws_ns=wpws,
        built_at=datetime.now(timezone.utc).isoformat(),scope='Explicit user-requested swapped-pin version-query trial; no motion',
        reports={name:digest(args.build/name) for name in ('verified_timing.rpt','verified_drc.rpt','verified_io.rpt','verified_route.rpt','verified_bus_skew.rpt')})
    m['rail_uart'].update(ports=SWAPPED_PORTS,pin_map='swapped',tx_drive_ma=4,
        swapped_design_checks='RAIL_UART_SWAPPED_DESIGN_CHECKS_PASS')
    m['source_inputs']={str(p.relative_to(root)).replace('\\','/'):digest(p) for p in (
        root/'shadow_play/hardware/rail_uart/build_swapped_pins.tcl',
        root/'shadow_play/hardware/rail_uart/rail_uart_swapped_pins.xdc',
        standard/'servo10_dual_uart.manifest.json')}
    m['source_checkpoint_sha256']=digest(root/'.review_work/rail_uart_20261019/dual_uart_verified.dcp')
    verify_swapped(m,digest(image))
    args.release.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(image,args.release/image.name)
    save(args.release/'servo10_uart_swapped.manifest.json',m)
    args.bundle.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.release/'servo10_uart_swapped.manifest.json',args.bundle/'servo10_uart_swapped.manifest.json')
    for name in ('zdt_readonly_protocol.py','zdt_uartlite_telemetry.py','load_rail_query_candidate.py','load_swapped_uart_candidate.py'):
        shutil.copyfile(root/'shadow_play/tools'/name,args.bundle/name)
    for name in ('mmio32.py','libservo_mmio32.so','servo_pwm_device.py'):
        target=args.bundle/'shadow_play/integrations/calibration'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'shadow_play/integrations/calibration'/name,target)
    (args.bundle/'shadow_play/integrations/calibration/.motion-inhibit').write_text('UART swapped-pin telemetry trial only.\n')
    code=(root/'shadow_play/integrations/follow/usb_hdmi.py').read_text(encoding='utf-8')
    if code.count(BASE_SHA)!=1:raise ValueError('Unexpected display hash gate')
    target=args.bundle/'shadow_play/integrations/follow/usb_hdmi.py'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(code.replace(BASE_SHA,m['sha256']),encoding='utf-8',newline='\n')
    for name in ('hdmi_sink.py','browser_display.py'):
        target=args.bundle/'shadow_play/hdmi_ui/runtime'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'shadow_play/hdmi_ui/runtime'/name,target)
    before,after=base.read_bytes(),image.read_bytes()
    if len(before)!=len(after):raise ValueError('Delta requires equal image lengths')
    (args.bundle/'image.xor.gz').write_bytes(gzip.compress(bytes(a^b for a,b in zip(before,after)),compresslevel=3,mtime=0))
    save(args.bundle/'DELTA.json',dict(base_sha256=STANDARD_SHA,target_sha256=m['sha256'],bytes=len(after),
        target_name=image.name,base_path='/run/media/mmcblk0p2/piying/rail-uart-query-20261019/servo10_dual_uart.bit.bin'))
    entries={str(p.relative_to(args.bundle)).replace('\\','/'):digest(p) for p in args.bundle.rglob('*') if p.is_file()}
    entries[image.name]=m['sha256']
    save(args.bundle/'MANIFEST.json',dict(files=entries,image_sha=m['sha256'],motion_enabled=False,
        automatic_start=False,pin_map='swapped',image_reconstructed_from_checked_delta=True))
    archive=args.bundle.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
        for p in sorted(args.bundle.rglob('*')):
            if p.is_file():tar.add(p,arcname=str(p.relative_to(args.bundle)).replace('\\','/'))
    print(json.dumps(dict(result='SWAPPED_UART_PACKAGED_NOT_LOADED',image_sha=m['sha256'],
        archive_sha256=digest(archive),archive_bytes=archive.stat().st_size,
        delta_bytes=(args.bundle/'image.xor.gz').stat().st_size,wns_ns=wns,whs_ns=whs,wpws_ns=wpws)))


if __name__=='__main__':main()
