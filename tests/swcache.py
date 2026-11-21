# The service worker's current cache name, read from sw.js, so no suite pins it by hand.
# Use: sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE
import pathlib, re

_SW = pathlib.Path(__file__).resolve().parent.parent / "sw.js"


def sw_cache():
    m = re.search(r'^const CACHE = "([^"]+)";', _SW.read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("no 'const CACHE = \"...\";' line in sw.js")
    return m.group(1)


SW_CACHE = sw_cache()
