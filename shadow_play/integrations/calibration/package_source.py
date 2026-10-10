"""Create a source handoff archive, excluding builds and recorded sessions."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path)
parser.add_argument("--replace", action="store_true", help="Replace a previously generated archive")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
destination = args.destination.resolve()
destination.parent.mkdir(parents=True, exist_ok=True)
allowed = {"assets", "config", "docs", "include", "integrations", "src", "tests", "third_party"}
files = [root / "CMakeLists.txt", root / "README.md", root / ".gitignore"]
for name in sorted(allowed):
    files.extend(p for p in (root / name).rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
with ZipFile(destination, "w" if args.replace else "x", compression=ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, Path("shadow_play") / path.relative_to(root))
with ZipFile(destination, "r") as archive:
    if archive.testzip() is not None:
        raise RuntimeError("Archive CRC check failed")
print(f"Created {destination}: {len(files)} source files")
