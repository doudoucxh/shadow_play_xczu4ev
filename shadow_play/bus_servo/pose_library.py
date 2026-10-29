"""Named feedback poses for the drawing catalog. No device I/O or PWM migration."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .editing import digest, utc, validate_pose
from .model import finite

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'shadow.bus-pose-library.v1'


def load_catalog():
    catalog = json.loads((ROOT / 'hdmi_ui/source/catalog.json').read_text(encoding='utf-8-sig'))
    rows = [dict(row, key='wusong/' + row['id'], actor='武松', axes=list(range(1, 7)))
            for row in catalog['actions']]
    rows.append(dict(key='tiger/neutral', id='neutral', name='站立', actor='老虎',
                     axes=list(range(7, 11)), pose=None,
                     instruction='手动摆好老虎站立姿势，再读取四台舵机的实际位置。'))
    return catalog['catalog_id'], {row['key']: row for row in rows}


class PoseLibrary:
    def __init__(self, profile, data=None):
        self.profile = profile
        self.catalog_id, self.catalog = load_catalog()
        if profile.layout.name != 'dual':
            raise ValueError('画画动作库使用当前人物 / 老虎双总线配置。')
        self.data = copy.deepcopy(data) if data is not None else {
            'schema': SCHEMA, 'catalog_id': self.catalog_id,
            'profile_sha256': profile.fingerprint, 'created_utc': utc(), 'poses': {}}
        self.validate()

    def validate(self):
        d = self.data
        if (d.get('schema') != SCHEMA or d.get('catalog_id') != self.catalog_id
                or d.get('profile_sha256') != self.profile.fingerprint):
            raise ValueError('动作库版本、画画目录或舵机配置不匹配。')
        if not isinstance(d.get('poses'), dict) or set(d['poses']) - set(self.catalog):
            raise ValueError('动作库包含未知动作。')
        for key, entry in d['poses'].items():
            pose = entry['pose']
            validate_pose(pose, self.profile)
            if pose['selected'] != self.catalog[key]['axes']:
                raise ValueError('动作必须包含对应角色的全部舵机，且顺序一致。')
            if entry.get('pose_sha256') != digest(pose):
                raise ValueError('姿势数据摘要不符。')
            if not isinstance(entry.get('note', ''), str) or len(entry.get('note', '')) > 2000:
                raise ValueError('动作备注最多2000字。')
        return self

    def set_pose(self, key, pose, note=''):
        if key not in self.catalog:
            raise ValueError('未知动作。')
        previous = copy.deepcopy(self.data)
        self.data['poses'][key] = {'pose': copy.deepcopy(pose), 'pose_sha256': digest(pose),
                                   'note': note, 'updated_utc': utc()}
        try:
            self.validate()
        except Exception:
            self.data = previous
            raise

    def get_pose(self, key, live=False):
        self.validate()
        entry = self.data['poses'].get(key)
        if entry is None:
            raise ValueError('这个动作还没有录入位置。')
        if live and entry['pose']['source'] != 'servo_feedback':
            raise ValueError('这是模拟姿势，请在实物模式重新读取保存后再调用。')
        return copy.deepcopy(entry['pose'])


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def save_library(path, library, expected_sha):
    """Atomic replace; retain old versions and refuse another window's changes."""
    library.validate()
    path = Path(path)
    if file_sha(path) != expected_sha:
        raise ValueError('文件已被另一窗口修改，请另存或重新打开，避免覆盖新记录。')
    raw = (json.dumps(library.data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        history = path.parent / (path.stem + '.history')
        history.mkdir(exist_ok=True)
        backup = history / (expected_sha + '.json')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return hashlib.sha256(raw).hexdigest()


def move_targets(session, targets, minimum_seconds=2):
    """Fresh start feedback and original manual-motion limits, not playback policy."""
    finite(minimum_seconds, .02, 9.999, '到达时间')
    numbers = [int(n) for n in targets]
    session.profile.select(numbers)
    for key, value in targets.items():
        session.profile.axes[int(key)].check_position(value)
    before = session.read(numbers)
    seconds = max(minimum_seconds, max(
        abs(session.profile.axes[n].degrees(targets[str(n)]) -
            session.profile.axes[n].degrees(before[n]['p'])) / session.profile.axes[n].max_speed
        for n in numbers) + .3)
    if seconds > 9.999:
        raise ValueError('到达距离过远，请分步设置角度接近目标。')
    if session.cancel_requested():
        raise ValueError('已取消，未发送目标。')
    # move() rechecks fresh feedback before sending. Keep its existing safeguards.
    session.move(targets, round(seconds * 1000))
    return seconds
