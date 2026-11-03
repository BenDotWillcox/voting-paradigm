"""Serve benchmark artifacts locally with their precompressed gzip siblings."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO


class GzipArtifactHandler(SimpleHTTPRequestHandler):
    def send_head(self) -> BinaryIO | None:
        path = Path(self.translate_path(self.path))
        compressed = path.with_suffix(path.suffix + ".gz")
        if path.suffix in (".json", ".geojson") and compressed.is_file() and "gzip" in self.headers.get("Accept-Encoding", ""):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(compressed.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return compressed.open("rb")
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".cache/kansas-block-benchmark/run-435"))
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_dir():
        parser.error(f"Missing benchmark directory: {directory}")
    handler = partial(GzipArtifactHandler, directory=str(directory))
    print(f"Serving {directory} at http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
