"""Package a checked bus candidate plus the PC/board sources, never deploy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import xml.etree.ElementTree as ET
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shadow_play.bus_servo.layouts import LAYOUTS, get_layout


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def ports(path):
    result={}
    for line in path.read_text().splitlines():
        cells=[c.strip() for c in line.split('|')]
        if len(cells)>7 and re.fullmatch(r'[A-Z]{1,2}[0-9]+',cells[1]) and cells[2]:
            result[cells[2]]=(cells[1],cells[5],cells[6])
    if len(result)<20:raise ValueError('Incomplete I/O report')
    return result


def package(build,release,bundle,root,layout_name='dual'):
    layout=get_layout(layout_name)
    tiger=layout_name=='tiger-four-port'
    ten=layout_name=='ten-port'
    stem='bus_servo_ten' if ten else ('bus_servo_tiger' if tiger else 'bus_servo')
    prefix='TEN_PORT' if ten else ('TIGER_FOUR' if tiger else 'BUS_SERVO')
    log=(root/f'.review_work/{stem}_build.log').read_text()
    sim=(root/f'.review_work/{stem}_sim.log').read_text()
    if not re.search(rf'^{prefix}_CANDIDATE_PASS WNS=',log,re.M) or not re.search(rf'^{prefix}_RTL_PASS:',sim,re.M):
        raise ValueError('Build and behavioral simulation must both pass')
    lines=(build/'timing.rpt').read_text().splitlines()
    line=next(i for i,s in enumerate(lines) if 'WNS(ns)' in s and 'WPWS(ns)' in s)
    values=lines[line+2].split()
    wns,whs,wpws=[float(values[i]) for i in (0,4,8)]
    if min(wns,whs,wpws)<0 or any(int(values[i]) for i in (2,6,10)):
        raise ValueError('Failing timing endpoints')
    baseline=json.loads((root/'shadow_play/hardware/bus_servo/baseline_rail_io.json').read_text())
    old={name:tuple(values) for name,values in baseline['ports'].items()}
    new=ports(build/'io.rpt')
    removed={f'servo_pwm[{i}]' for i in range(10)}
    physical={name+'_servo_bus':pin for name,pin,_ in layout.buses}
    if set(old)-set(new)!=removed or set(new)-set(old)!=set(physical):
        raise ValueError('Unexpected physical port additions/removals')
    if any(new[name]!=old[name] for name in set(old)&set(new)):
        raise ValueError('An unrelated camera/HDMI/rail/PS pin changed')
    for name,pin in physical.items():
        if new[name]!=(pin,'BIDIR','LVCMOS33'):raise ValueError('Wrong bus I/O direction or level')
    handoff=ET.parse(build/'bus_servo/bus_servo.gen/sources_1/bd/system/hw_handoff/system.hwh')
    ranges=[n for n in handoff.iter('MEMRANGE') if n.get('INSTANCE')=='bus_servo_0']
    if not ranges or not any(int(n.get('BASEVALUE','-1'),0)==0xA0060000 for n in ranges):
        raise ValueError('Bus candidate address mismatch')
    image=build/'bus_servo.bit.bin'
    if not image.is_file():raise ValueError('Convert verified .bit with bootgen first')
    inputs=[p for p in (root/f'shadow_play/hardware/{stem}').iterdir() if p.suffix in ('.v','.tcl','.xdc','.json')]
    if tiger or ten:
        inputs += [root/'shadow_play/hardware/bus_servo'/name for name in
                   ('single_wire_uart.v','base_dual_rail_design.tcl','baseline_rail_io.json')]
    manifest={'schema':'shadow.bus-image.v1','identity':layout.identity,'layout':layout.name,'checks':'passed','register_base':0xA0060000,
              'pins':layout.pins,'clock_hz':100000000,'baudrate':115200,
              'legacy_pwm_connected':False,'physical_hardware_tested':False,'sha256':sha(image),
              'wns_ns':wns,'whs_ns':whs,'wpws_ns':wpws,'part':'xczu4ev-sfvc784-2-i',
              'watchdog_seconds':1,'watchdog_action':'one broadcast PULK per bus; actual servo response unverified',
              'preserved_io_count':len(set(old)&set(new)),
              'baseline_io_report_sha256':baseline['report_sha256'],
              'reports':{name:sha(build/name) for name in ('timing.rpt','drc.rpt','route.rpt','bus_skew.rpt','io.rpt')},
              'sources':{str(p.relative_to(root)).replace('\\','/'):sha(p) for p in inputs}}
    release.mkdir(parents=True,exist_ok=False)
    shutil.copy2(image,release/image.name)
    (release/'bus_servo.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    bundle.mkdir(parents=True,exist_ok=False)
    for p in release.iterdir():shutil.copy2(p,bundle/p.name)
    source_files=list((root/'shadow_play/bus_servo').glob('*.py'))
    profile_name='bus_servo_ten_port.json' if ten else ('bus_servo_tiger_four.json' if tiger else 'bus_servo.json')
    source_files += [root/'shadow_play/config'/profile_name, root/'shadow_play/integrations/calibration/mmio32.py',root/'shadow_play/integrations/calibration/libservo_mmio32.so']
    for p in source_files:
        dest=bundle/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    startup='start_ten_console.sh' if ten else ('start_tiger_console.sh' if tiger else 'start_console.sh')
    shutil.copy2(root/'shadow_play/bus_servo'/startup,bundle/'start_console.sh')
    # Preserve the existing HDMI runtime's exact-image gate in an isolated copy.
    source=root/'shadow_play/integrations/follow/usb_hdmi.py'
    old_sha='824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
    code=source.read_text(encoding='utf-8')
    if code.count(old_sha)!=1:raise ValueError('Review HDMI image gate before packaging')
    dest=bundle/source.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(code.replace(old_sha,manifest['sha256']).replace('/run/shadow-pwm-loaded.json','/run/shadow-bus-servo-loaded.json'),encoding='utf-8',newline='\n')
    for name in ('hdmi_sink.py','browser_display.py'):
        p=root/'shadow_play/hdmi_ui/runtime'/name;dest=bundle/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    files={str(p.relative_to(bundle)).replace('\\','/'):sha(p) for p in bundle.rglob('*') if p.is_file()}
    (bundle/'MANIFEST.json').write_text(json.dumps({'files':files,'automatic_start':False,'deployed':False},indent=2)+'\n',encoding='utf-8',newline='\n')
    archive=bundle.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():tar.add(p,arcname=str(p.relative_to(bundle)).replace('\\','/'))
    return dict(manifest_sha=sha(release/'bus_servo.manifest.json'),image_sha=manifest['sha256'],
                files=len(files),archive=str(archive),wns_ns=wns,whs_ns=whs,wpws_ns=wpws)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',required=True,type=Path)
    parser.add_argument('--release',required=True,type=Path)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--layout',choices=list(LAYOUTS),default='dual')
    args=parser.parse_args()
    print(json.dumps(package(args.build,args.release,args.bundle,Path(__file__).resolve().parents[2],args.layout)))


if __name__=='__main__':main()
