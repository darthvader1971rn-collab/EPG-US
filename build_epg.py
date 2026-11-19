import gzip
import shutil
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CHANNELS_FILE = Path("channels.txt")
OUTPUT_EPG = Path("epg_usa.xml.gz")

EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
    # Gdy w przyszłości dopiszesz do channels.txt kanały z US2, odkomentuj linię poniżej:
    # "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def load_target_ids(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Brak pliku: {path}")
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            ids.add(clean)
    return ids


def is_gzip_file(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(2) == b"\x1f\x8b"


def download_file(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def filter_source(
    source_path: Path,
    target_ids: set[str],
    seen_channels: set[str],
    channels_xml: list[bytes],
    prog_out,
) -> tuple[int, int]:
    opener = gzip.open if is_gzip_file(source_path) else open
    ch_cnt = 0
    pr_cnt = 0

    with opener(source_path, "rb") as f:
        context = ET.iterparse(f, events=("start", "end"))
        try:
            _, root = next(context)
        except StopIteration:
            return 0, 0

        for event, elem in context:
            if event != "end":
                continue

            if elem.tag == "channel":
                cid = elem.get("id")
                if cid in target_ids and cid not in seen_channels:
                    seen_channels.add(cid)
                    channels_xml.append(ET.tostring(elem, encoding="utf-8"))
                    ch_cnt += 1
                root.clear()

            elif elem.tag == "programme":
                cid = elem.get("channel")
                if cid in target_ids:
                    prog_out.write(b"  ")
                    prog_out.write(ET.tostring(elem, encoding="utf-8"))
                    prog_out.write(b"\n")
                    pr_cnt += 1
                root.clear()

    return ch_cnt, pr_cnt


def main():
    target_ids = load_target_ids(CHANNELS_FILE)
    print(f"Wczytano {len(target_ids)} kanałów z {CHANNELS_FILE.name}.")

    seen_channels: set[str] = set()
    channels_xml: list[bytes] = []
    total_programmes = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        prog_tmp = tmp_path / "programmes.tmp"

        with open(prog_tmp, "wb") as prog_f:
            for idx, url in enumerate(EPG_URLS, start=1):
                print(f"[{idx}/{len(EPG_URLS)}] Pobieranie: {url}")
                dl_path = tmp_path / f"src_{idx}.bin"
                try:
                    download_file(url, dl_path)
                    ch_cnt, pr_cnt = filter_source(
                        dl_path, target_ids, seen_channels, channels_xml, prog_f
                    )
                    total_programmes += pr_cnt
                    print(f"    Dopasowano: {ch_cnt} kanałów, {pr_cnt} audycji.")
                except Exception as e:
                    print(f"    BŁĄD: {e}")
                finally:
                    if dl_path.exists():
                        dl_path.unlink()

        with gzip.open(OUTPUT_EPG, "wb", compresslevel=6) as out_gz:
            out_gz.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            out_gz.write(b'<tv generator-info-name="Custom USA EPG">\n')
            for ch_bytes in channels_xml:
                out_gz.write(b"  ")
                out_gz.write(ch_bytes)
                out_gz.write(b"\n")
            with open(prog_tmp, "rb") as prog_in:
                shutil.copyfileobj(prog_in, out_gz)
            out_gz.write(b"</tv>\n")

    size_kb = OUTPUT_EPG.stat().st_size / 1024
    print(f"GOTOWE: {OUTPUT_EPG} ({size_kb:.1f} KB) | Kanały: {len(seen_channels)}/{len(target_ids)} | Audycje: {total_programmes}")


if __name__ == "__main__":
    main()