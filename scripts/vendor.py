"""One-time maintainer download. The running app never contacts a CDN."""
from pathlib import Path
from urllib.request import urlopen
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1] / "web" / "vendor"
SOURCES = {
    "three.module.js": "https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.js",
    "three.LICENSE": "https://cdn.jsdelivr.net/npm/three@0.160.1/LICENSE",
    "3d-force-graph.min.js": "https://cdn.jsdelivr.net/npm/3d-force-graph@1.79.0/dist/3d-force-graph.min.js",
    "3d-force-graph.LICENSE": "https://cdn.jsdelivr.net/npm/3d-force-graph@1.79.0/LICENSE",
}

if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in SOURCES.items():
        with urlopen(url, timeout=30) as response:
            data = response.read()
        (ROOT / name).write_bytes(data)
        manifest[name] = {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        print(f"Vendored {name}: {len(data)} bytes")
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

