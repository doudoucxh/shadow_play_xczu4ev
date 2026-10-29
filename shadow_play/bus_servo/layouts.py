"""Fixed, reviewed wiring layouts; physical connectors are not servo IDs."""
from dataclasses import dataclass


BASE = 0xA0060000


@dataclass(frozen=True)
class Layout:
    name: str
    identity: str
    buses: tuple  # (bus name, package pin, original connector)
    axis_buses: tuple  # (logical axis, bus name)
    board_directory: str
    title: str

    @property
    def word(self):
        return int.from_bytes(self.identity.encode('ascii'), 'big')

    @property
    def pins(self):
        return {name: pin for name, pin, _ in self.buses}

    @property
    def offsets(self):
        return {name: (i + 1) * 0x100 for i, (name, _, _) in enumerate(self.buses)}

    @property
    def numbers(self):
        return [n for n, _ in self.axis_buses]

    def connector_label(self, bus):
        return next(f'原{connector}口 · {pin}' for name, pin, connector in self.buses if name == bus)


LAYOUTS = {
    'dual': Layout('dual', 'BS10', (('person', 'E14', 9), ('tiger', 'E15', 10)),
                   tuple((n, 'person' if n <= 6 else 'tiger') for n in range(1, 11)),
                   'bus-servo-dual-console-v1', '人物6轴 / 原9口   老虎4轴 / 原10口'),
    'tiger-four-port': Layout('tiger-four-port', 'BT04',
                   (('tiger7', 'D14', 1), ('tiger8', 'D15', 2),
                    ('tiger9', 'F13', 3), ('tiger10', 'G13', 4)),
                   tuple((n, f'tiger{n}') for n in range(7, 11)),
                   'bus-servo-tiger-four-v1', '老虎临时四口：7→原1口  8→原2口  9→原3口  10→原4口'),
    'ten-port': Layout('ten-port', 'BP10',
                   tuple((f'servo{n}', pin, n) for n, pin in enumerate(
                       ('D14','D15','F13','G13','G14','G15','J14','E13','E14','E15'), 1)),
                   tuple((n, f'servo{n}') for n in range(1, 11)),
                   'bus-servo-ten-port-v1', '十路独立信号：人物1～6→原1～6口 · 老虎7～10→原7～10口'),
}


def get_layout(name='dual'):
    if not isinstance(name, str) or name not in LAYOUTS:
        raise ValueError('Unknown bus wiring layout')
    return LAYOUTS[name]


def manifest_layout(manifest):
    layout = get_layout(manifest.get('layout', 'dual'))
    if (manifest.get('identity') != layout.identity or manifest.get('pins') != layout.pins
            or manifest.get('register_base') != BASE or manifest.get('clock_hz') != 100000000
            or manifest.get('baudrate') != 115200 or manifest.get('checks') != 'passed'
            or manifest.get('legacy_pwm_connected') is not False):
        raise ValueError('Image identity / pin map / clock does not match its wiring layout')
    return layout
