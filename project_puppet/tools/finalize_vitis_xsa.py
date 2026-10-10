"""Add the top-module metadata omitted by checkpoint-based Vivado 2022.2 XSA export.

Vivado's implemented-checkpoint export contains the verified bitstream and
sysdef HwDb, but omits TopModuleName.  Vitis 2022.2 requires all three.  This
repackages only xsa.json/xsa.xml; hardware payloads are copied byte-for-byte.
"""

from __future__ import annotations

import json
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
BUILD = PROJECT / "ultral_xczu4ev" / "dpu" / "build"
SOURCE = BUILD / "Shadow_ultra_dpu_b4096.xsa"
OUTPUT = BUILD / "Shadow_ultra_dpu_b4096_vitis.xsa"
TOP = "system_wrapper"


def main() -> None:
    with zipfile.ZipFile(SOURCE, "r") as archive:
        names = set(archive.namelist())
        required = {"sysdef.xml", "system.hwh", "xsa.json", "xsa.xml"}
        missing = required - names
        if missing:
            raise RuntimeError(f"implemented XSA is missing: {sorted(missing)}")
        json_data = json.loads(archive.read("xsa.json"))
        xml_root = ET.fromstring(archive.read("xsa.xml"))
        json_data["topModuleName"] = TOP
        build = xml_root.find("./DSA/Build")
        if build is None:
            raise RuntimeError("xsa.xml has no DSA/Build element")
        build.set("TopModuleName", TOP)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xsa", dir=BUILD) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for item in archive.infolist():
                    if item.filename == "xsa.json":
                        payload = json.dumps(json_data, indent=4).encode("utf-8") + b"\n"
                    elif item.filename == "xsa.xml":
                        payload = ET.tostring(xml_root, encoding="utf-8", xml_declaration=True)
                    else:
                        payload = archive.read(item.filename)
                    output.writestr(item, payload)
            temporary_path.replace(OUTPUT)
        finally:
            temporary_path.unlink(missing_ok=True)
    print(f"Created Vitis-readable implemented XSA: {OUTPUT}")


if __name__ == "__main__":
    main()
