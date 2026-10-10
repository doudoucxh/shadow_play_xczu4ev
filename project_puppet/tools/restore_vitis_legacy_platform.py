"""Restore the relocated standalone camera platform without touching DPU release files."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
PLATFORM = (
    PROJECT
    / "ultral_xczu4ev"
    / "vitis_workspace_2022_2"
    / "Shadow_ultra_platform"
)
PLATFORM_SPR = PLATFORM / "platform.spr"
LEGACY_XSA = PLATFORM / "hw" / "Shadow_ultra.xsa"


def main() -> None:
    if not LEGACY_XSA.is_file():
        raise FileNotFoundError(LEGACY_XSA)
    data = json.loads(PLATFORM_SPR.read_text(encoding="utf-8"))
    data["platHandOff"] = LEGACY_XSA.as_posix()
    data["platIntHandOff"] = "<platformDir>/hw/Shadow_ultra.xsa"
    PLATFORM_SPR.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Restored standalone platform handoff: {data['platHandOff']}")


if __name__ == "__main__":
    main()
