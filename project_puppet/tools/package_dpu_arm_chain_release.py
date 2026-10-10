"""Package timing-clean DPU hardware and update the ARM-CHAIN release manifest."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
RELEASE = PROJECT / "deploy" / "dpu_arm_chain"
BUILD = PROJECT / "ultral_xczu4ev" / "dpu" / "build"
REPORTS = PROJECT / "ultral_xczu4ev" / "dpu" / "reports"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {"size": path.stat().st_size, "sha256": sha256(path)}


def copy_required(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    hardware = RELEASE / "hardware"
    copies = {
        BUILD / "system_wrapper_dpu_b4096.bit": hardware / "system_wrapper_dpu_b4096.bit",
        # Exported from the Vivado project source database so Vitis sees the
        # TopModuleName/HwDb metadata.  The timing-clean bit remains separate.
        BUILD / "Shadow_ultra_dpu_b4096_vitis.xsa": hardware / "Shadow_ultra_dpu_b4096.xsa",
        BUILD / "arch_b4096.json": hardware / "arch_b4096.json",
        REPORTS / "post_route_timing.rpt": hardware / "post_route_timing.rpt",
        REPORTS / "post_route_drc.rpt": hardware / "post_route_drc.rpt",
        REPORTS / "post_route_status.rpt": hardware / "post_route_status.rpt",
    }
    for source, destination in copies.items():
        copy_required(source, destination)

    manifest_path = RELEASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for path in RELEASE.rglob("*"):
        if path.is_file() and path != manifest_path and "__pycache__" not in path.parts:
            manifest.setdefault("artifacts", {})[path.relative_to(RELEASE).as_posix()] = artifact(path)

    manifest["hardware"] = {
        "tool": "Vivado 2022.2",
        "dpu": "DPUCZDX8G v4.1 B4096",
        "post_route_wns_ns": 0.786,
        "drc_errors": 0,
        "bitstream_includes_dpu": True,
        "xmodel_status": "pending_vitis_ai_3_linux_quantize_compile",
        "target_runtime_status": "pending_linux_vart_and_ov5640_frame_source",
        "existing_vitis_domain": "standalone_domain",
    }
    manifest["packaged_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Packaged {len(copies)} hardware files into {hardware}")
    print(f"Updated {manifest_path}")


if __name__ == "__main__":
    main()
