"""Download and verify immutable upstream source artifacts; never use floating main."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

REVISION = "801592132bfd833f049b517a4e013e00a5fc40fa"
FILES = {
    "datasets/test_data.csv": "9d296b09668d945d7c4ad8136032e984a3a3b8b0a7b046eb0f9f787331d9d97d",
    "evaluation/evaluate.py": "e165e10cb1db77f7a1d97c6f386524547ce90d77ce56ae4d95f7544ad9320a1a",
    "evaluation/generate_code_prompt.py": "cb48b90779a0e742d5228bb0cc40f59edd6bfc126637c8134d401825888d82ad",
}

def load_source(cache: Path) -> dict[str, Path]:
    result = {}
    for name, digest in FILES.items():
        path = cache / REVISION / name
        if not path.exists():
            url = f"https://raw.githubusercontent.com/nikhilk7153/MedCalc-Bench-Verified/{REVISION}/{name}"
            data = urlopen(url, timeout=60).read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Upstream digest mismatch: {name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Cached digest mismatch: {name}")
        result[name] = path
    return result
