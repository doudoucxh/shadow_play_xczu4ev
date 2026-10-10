"""Point the relocated Vitis 2022.2 platform at the timing-clean DPU XSA."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
PLATFORM_SPR = (
    PROJECT
    / "ultral_xczu4ev"
    / "vitis_workspace_2022_2"
    / "Shadow_ultra_platform"
    / "platform.spr"
)
XSA = (
    PROJECT
    / "deploy"
    / "dpu_arm_chain"
    / "hardware"
    / "Shadow_ultra_dpu_b4096.xsa"
)


def main() -> None:
    if not XSA.is_file():
        raise FileNotFoundError(XSA)
    data = json.loads(PLATFORM_SPR.read_text(encoding="utf-8"))
    data["platHandOff"] = XSA.as_posix()
    data["platIntHandOff"] = "<platformDir>/hw/Shadow_ultra_dpu_b4096.xsa"
    PLATFORM_SPR.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"platHandOff={data['platHandOff']}")
    print(f"platIntHandOff={data['platIntHandOff']}")


if __name__ == "__main__":
    main()
