#!/usr/bin/env python3
"""Build NOWBAT's public ZIP files from an explicit allowlist.

No development files, tests or host diagnostics are included in either ZIP.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "DIST"
SOURCE_FILES = (
    ".gitignore", "LICENSE", "README.md", "README.TXT", "SCRIPT.TXT", "MAKE.BAT",
    "SRC/WAS.ASM", "SRC/WASFS.ASM", "SRC/WASSNAP.ASM",
    "SRC/WASTAR.ASM", "SRC/WASUI.ASM",
    "LINK/WIN101.RSP", "LINK/WIN300.RSP",
    "ASSETS/WIN101.ICO", "ASSETS/WIN300.ICO",
    "HOST/iconbuild.py", "HOST/packdist.py",
    "EXAMPLES/HELLO.WAS", "EXAMPLES/CAPTURE.WAS", "EXAMPLES/FILECOPY.WAS",
)
BINARY_FILES = (
    "LICENSE", "README.TXT", "SCRIPT.TXT",
    "EXAMPLES/HELLO.WAS", "EXAMPLES/CAPTURE.WAS", "EXAMPLES/FILECOPY.WAS",
    "DIST/WIN101/NOWBAT.EXE", "DIST/WIN300/NOWBAT.EXE",
)


def check_exe(path: Path):
    blob = path.read_bytes()
    if len(blob) < 0x44 or blob[:2] != b"MZ":
        raise ValueError(f"{path}: not an MZ executable")
    offset = struct.unpack_from("<I", blob, 0x3C)[0]
    if offset >= len(blob) - 2 or blob[offset:offset + 2] != b"NE":
        raise ValueError(f"{path}: not a Windows NE executable")


def write_zip(name: str, files: tuple[str, ...]):
    output = DIST / name
    tmp = DIST / (name + ".tmp")
    try:
        with ZipFile(tmp, "w", ZIP_DEFLATED, compresslevel=9) as z:
            for rel in files:
                f = ROOT / rel
                if not f.is_file():
                    raise FileNotFoundError(f"Required public file missing: {rel}")
                member = rel[5:] if rel.startswith("DIST/") else rel
                z.write(f, arcname="NOWBAT/" + member)
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"{output.relative_to(ROOT)}: {len(files)} files ({output.stat().st_size} bytes)")


def main():
    DIST.mkdir(exist_ok=True)
    try:
        for path in (DIST / "WIN101/NOWBAT.EXE", DIST / "WIN300/NOWBAT.EXE"):
            check_exe(path)
        write_zip("NOWBAT_SOURCE.ZIP", SOURCE_FILES)
        write_zip("NOWBAT_BINARIES.ZIP", BINARY_FILES)
    except (OSError, ValueError) as exc:
        for name in ("NOWBAT_SOURCE.ZIP", "NOWBAT_BINARIES.ZIP"):
            (DIST / name).unlink(missing_ok=True)
        print("MAKE FAIL: public ZIP packaging failed:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
