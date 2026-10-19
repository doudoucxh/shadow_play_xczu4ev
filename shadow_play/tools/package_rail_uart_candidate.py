"""Package only a successfully validated dual-UART build; never connects to hardware."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import xml.etree.ElementTree as ET

from load_rail_query_candidate import BASE_SHA, PINS, PORTS, verify_candidate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


def io_ports(path):
    ports = {}
    for line in path.read_text().splitlines():
        cells = [part.strip() for part in line.split('|')]
        if len(cells) > 7 and re.fullmatch(r'[A-Z]{1,2}[0-9]+', cells[1]) and cells[2]:
            ports[cells[2]] = (cells[1], cells[5], cells[6])
    if len(ports) < 20:
        raise ValueError('Incomplete reference/candidate I/O report')
    return ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--build-log', type=Path, required=True)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    log = args.build_log.read_text(encoding='utf-8')
    for token in ('SERVO_IMAGE_DESIGN_CHECKS_PASS', 'RAIL_UART_DESIGN_CHECKS_PASS', 'RAIL_UART_BITSTREAM_READY'):
        if not re.search('^'+token+'$', log, re.M):
            raise ValueError('Build has not completed required check: '+token)
    lines = (args.build/'verified_timing.rpt').read_text().splitlines()
    header = next(i for i, line in enumerate(lines) if 'WNS(ns)' in line and 'WPWS(ns)' in line)
    timing = lines[header+2].split()
    wns, whs, wpws = (float(timing[i]) for i in (0, 4, 8))
    if min(wns, whs, wpws) < 0 or any(int(timing[i]) for i in (2, 6, 10)):
        raise ValueError('Timing summary has failing endpoints')
    reference = root/'.review_work/servo_pin4_g13_20261010/fpga'
    if sha(reference/'servo10_vision.bit.bin') != BASE_SHA:
        raise ValueError('Reference image is not the approved G13 image')
    old_ports = io_ports(reference/'verified_io.rpt')
    new_ports = io_ports(args.build/'verified_io.rpt')
    if (any(new_ports.get(name) != value for name, value in old_ports.items()) or
            set(new_ports)-set(old_ports) != {'person_uart_tx', 'person_uart_rx', 'tiger_uart_tx', 'tiger_uart_rx'}):
        raise ValueError('An existing port changed or an unexpected port was added')
    handoff = ET.parse(args.build/'servo10_dual_uart/servo10_dual_uart.gen/sources_1/bd/system/hw_handoff/system.hwh')
    serial_clock = {}
    for name, port in PORTS.items():
        xci = args.build/('servo10_dual_uart/servo10_dual_uart.srcs/sources_1/bd/system/ip/system_%s_uart_0/system_%s_uart_0.xci' % (name, name))
        p = json.loads(xci.read_text())['ip_inst']['parameters']['model_parameters']
        values = {key: int(p[key][0]['value']) for key in ('C_BAUDRATE', 'C_DATA_BITS', 'C_USE_PARITY', 'C_S_AXI_ACLK_FREQ_HZ')}
        if (values['C_BAUDRATE'] != 115200 or values['C_DATA_BITS'] != 8 or values['C_USE_PARITY'] != 0 or
                abs(values['C_S_AXI_ACLK_FREQ_HZ']-100000000) > 1000):
            raise ValueError('Generated UART settings/clock mismatch')
        serial_clock[name] = values['C_S_AXI_ACLK_FREQ_HZ']
        ranges = [node for node in handoff.iter('MEMRANGE') if node.get('INSTANCE') == name+'_uart']
        if not ranges or not any(int(node.get('BASEVALUE', '-1'), 0) == port['base'] for node in ranges):
            raise ValueError('Handoff UART address mismatch: '+name)
    image = args.build/'servo10_dual_uart.bit.bin'
    if not image.is_file():
        raise ValueError('Convert the checked bitstream with bootgen first')
    manifest = dict(image_kind='servo10_vision', design_checks='SERVO_IMAGE_DESIGN_CHECKS_PASS',
        bus_skew_check='SERVO_BUS_SKEW_CHECK_PASS', register_base=0xA0030000, pins=PINS,
        sha256=sha(image), wns_ns=wns, whs_ns=whs, wpws_ns=wpws, part='xczu4ev-sfvc784-2-i',
        clock_hz=100000000, period_us=20000, channels=10, reset_outputs='disabled',
        previous_sha256=BASE_SHA, scope='Volatile UART telemetry commissioning; no boot changes or motion',
        built_at=datetime.now(timezone.utc).isoformat(),
        rail_uart=dict(design_checks='RAIL_UART_DESIGN_CHECKS_PASS', ports=PORTS, baud=115200,
                       format='8N1', generated_clock_hz=serial_clock, reset_tx='idle_high_no_bytes'),
        reports={name:sha(args.build/name) for name in ('verified_timing.rpt', 'verified_drc.rpt',
            'verified_io.rpt', 'verified_route.rpt', 'verified_bus_skew.rpt')},
        design_export_sha256=sha(args.build/'dual_uart_design.tcl'),
        base_reference_io_sha256=sha(reference/'verified_io.rpt'),
        existing_ports_preserved=len(old_ports),
        source_inputs={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in [
            root/'shadow_play/hardware/rail_uart/create_project.tcl',
            root/'shadow_play/hardware/rail_uart/build_project.tcl',
            root/'shadow_play/hardware/rail_uart/rail_uart_pins.xdc',
            root/'shadow_play/hardware/servo_pwm/servo_pwm_axi.v',
            root/'shadow_play/hardware/servo_pwm/servo_pins.xdc']})
    verify_candidate(manifest, sha(image))
    args.release.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(image, args.release/image.name)
    save(args.release/'servo10_dual_uart.manifest.json', manifest)
    args.bundle.mkdir(parents=True, exist_ok=False)
    for p in args.release.iterdir():
        shutil.copyfile(p, args.bundle/p.name)
    for name in ('zdt_readonly_protocol.py', 'zdt_uartlite_telemetry.py', 'load_rail_query_candidate.py'):
        shutil.copyfile(root/'shadow_play/tools'/name, args.bundle/name)
    for name in ('mmio32.py', 'libservo_mmio32.so', 'servo_pwm_device.py'):
        dest = args.bundle/'shadow_play/integrations/calibration'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/'shadow_play/integrations/calibration'/name, dest)
    (args.bundle/'shadow_play/integrations/calibration/.motion-inhibit').write_text('UART telemetry commissioning only.\n')
    source = root/'shadow_play/integrations/follow/usb_hdmi.py'
    code = source.read_text(encoding='utf-8')
    if code.count(BASE_SHA) != 1:
        raise ValueError('Unexpected HDMI image gate source; refuse a broad replacement')
    dest = args.bundle/'shadow_play/integrations/follow/usb_hdmi.py'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(code.replace(BASE_SHA, manifest['sha256']), encoding='utf-8', newline='\n')
    for name in ('hdmi_sink.py', 'browser_display.py'):
        dest = args.bundle/'shadow_play/hdmi_ui/runtime'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/'shadow_play/hdmi_ui/runtime'/name, dest)
    entries = {str(p.relative_to(args.bundle)).replace('\\', '/'):sha(p) for p in args.bundle.rglob('*') if p.is_file()}
    save(args.bundle/'MANIFEST.json', dict(schema='rail-uart-query-bundle-v1', files=entries,
         image_sha=manifest['sha256'], motion_enabled=False, automatic_start=False,
         hdmi_change='Only the exact reviewed image hash in a separate copy; original SD code unchanged'))
    archive = args.bundle.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz', compresslevel=3) as tar:
        for p in sorted(args.bundle.rglob('*')):
            if p.is_file():
                tar.add(p, arcname=str(p.relative_to(args.bundle)).replace('\\', '/'))
    print(json.dumps(dict(result='CANDIDATE_PACKAGED_NOT_DEPLOYED', image_sha=manifest['sha256'],
        wns_ns=wns, whs_ns=whs, wpws_ns=wpws, files=len(entries), archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive))))


if __name__ == '__main__':
    main()
