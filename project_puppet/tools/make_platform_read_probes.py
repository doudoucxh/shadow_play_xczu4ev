"""Create isolated Vitis platform-read probes for old and DPU XSAs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
BASE_SPR = (
    PROJECT / "ultral_xczu4ev" / "vitis_workspace_2022_2" /
    "Shadow_ultra_platform" / "platform.spr"
)
PROBES = PROJECT / "ultral_xczu4ev" / "dpu" / "build" / "platform_probes"
SOURCES = {
    "old": PROJECT / "ultral_xczu4ev" / "vitis_workspace_2022_2" /
           "Shadow_ultra_platform" / "hw" / "Shadow_ultra.xsa",
    "dpu": PROJECT / "deploy" / "dpu_arm_chain" / "hardware" /
           "Shadow_ultra_dpu_b4096.xsa",
}


def main() -> None:
    base = json.loads(BASE_SPR.read_text(encoding="utf-8"))
    for label, source in SOURCES.items():
        target = PROBES / label
        hardware = target / "hw" / f"{label}.xsa"
        hardware.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, hardware)
        data = dict(base)
        data["platformName"] = f"probe_{label}"
        data["platformDesc"] = f"probe_{label}"
        data["platHandOff"] = hardware.as_posix()
        data["platIntHandOff"] = f"<platformDir>/hw/{label}.xsa"
        for system in data.get("systems", []):
            system["systemName"] = f"probe_{label}"
            system["systemDispName"] = f"probe_{label}"
        (target / "platform.spr").write_text(
            json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(target / "platform.spr")


if __name__ == "__main__":
    main()
