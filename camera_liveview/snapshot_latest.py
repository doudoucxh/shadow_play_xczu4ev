"""Copy a fresh SDK live-view frame for inspection without desktop capture."""
import json
import io
from pathlib import Path
import time
from PIL import Image

root = Path(__file__).resolve().parent
pointer = json.loads((root / 'output/current.json').read_text(encoding='utf-8-sig'))
session = Path(pointer['directory']).resolve()
assert session.parent == (root / 'output').resolve(), 'Unexpected session path'
state = json.loads((session / 'status.json').read_text(encoding='utf-8'))
age_ms = time.time() * 1000 - state['updated_unix_ms']
assert state['state'] == 'streaming', 'No active stream: ' + state['state']
assert -1000 <= age_ms <= 5000, 'Preview is stale; do not describe it as current'
data = (session / 'latest.jpg').read_bytes()
# Sony may append padding after JPEG's EOI marker. Decode the JPEG instead of
# assuming its last two buffer bytes are the marker.
with Image.open(io.BytesIO(data)) as image:
    assert image.format == 'JPEG', 'Unexpected preview format'
    image.load()
    width, height = image.size
snapshot = root / 'output/snapshot.jpg'
snapshot.write_bytes(data)
print(json.dumps(dict(path=str(snapshot), frames=state['frames'], age_ms=round(age_ms),
                     jpeg_bytes=len(data), width=width, height=height), ensure_ascii=False))
