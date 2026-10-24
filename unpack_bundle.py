import re
import sys
from pathlib import Path

BUNDLE_FILE = Path("jarvis_process_isolation.bundle")
FILE_PATTERN = re.compile(r'<file path="([^"]+)">\n?(.*?)\n?</file>', re.DOTALL)


def unpack(bundle_path: Path) -> None:
    if not bundle_path.exists():
        print(f"[ERROR] Bundle file not found: {bundle_path}")
        sys.exit(1)

    raw = bundle_path.read_text(encoding="utf-8")
    matches = FILE_PATTERN.findall(raw)
    if not matches:
        print("[ERROR] No <file> entries found in bundle.")
        sys.exit(1)

    for rel_path, content in matches:
        target = Path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"[UNPACKED] {target}")

    print(f"\nSuccessfully unpacked {len(matches)} files.")


if __name__ == "__main__":
    path_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else BUNDLE_FILE
    unpack(path_arg)