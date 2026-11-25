"""Archive only known obsolete private wave notes; never touch local config."""
from pathlib import Path

LEGACY_NOTES = ('START_HERE.TXT', 'W058_README.TXT', 'W059_README.TXT',
                'W060_README.TXT', 'W062_NOTES.TXT')


def archive_notes(root):
    history = root / 'DOCS' / 'HISTORY'
    for name in LEGACY_NOTES:
        src = root / name
        if not src.is_file():
            continue
        history.mkdir(parents=True, exist_ok=True)
        dst = history / name
        n = 1
        while dst.exists():
            if dst.is_file() and dst.read_bytes() == src.read_bytes():
                src.unlink()
                break
            dst = history / (src.stem + '_%d' % n + src.suffix)
            n += 1
        else:
            src.rename(dst)
        print('ROOT CLEANUP: %s -> %s' % (name, dst.relative_to(root)), flush=True)

    # Existing completed wave notes live in HISTORY, not the active DOCS list.
    for src in sorted(src for src in (root / 'DOCS').glob('W0[0-8][0-9]_*.TXT')
                      if src.name[:4] in ('W065','W066','W067','W068','W069','W070','W071','W072','W073','W074','W075','W076','W077','W078','W079','W080','W081','W082')):
        if not src.is_file():
            continue
        history.mkdir(parents=True, exist_ok=True)
        dst = history / src.name
        if not dst.exists():
            src.rename(dst)
        elif dst.is_file() and dst.read_bytes() == src.read_bytes():
            src.unlink()
