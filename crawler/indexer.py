import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
from flask import Flask, request, jsonify
import xxhash

load_dotenv()

ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://elasticsearch:9200")
DATA_FOLDER = os.getenv("DATA_FOLDER", "/app/data")
STATE_FOLDER = os.getenv("STATE_FOLDER", "/app/state")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "300"))
BULK_CHUNK = int(os.getenv("BULK_CHUNK", "500"))

Path(STATE_FOLDER).mkdir(parents=True, exist_ok=True)
STATE_FILE = Path(STATE_FOLDER) / "state.json"

es = Elasticsearch(ELASTIC_HOST)

app = Flask(__name__)

# State format: { "files": { "<relpath>": {"mtime": float, "size": int, "fingerprint": str} }, "last_indexed": <ts> }
if STATE_FILE.exists():
    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception:
        state = {"files": {}, "last_indexed": 0}
else:
    state = {"files": {}, "last_indexed": 0}

def fingerprint_file(path: Path):
    try:
        stat = path.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        h = xxhash.xxh64()
        with path.open("rb") as f:
            head = f.read(65536)
            if size > 131072:
                f.seek(max(0, size-65536))
                tail = f.read(65536)
                h.update(head)
                h.update(tail)
            else:
                h.update(head)
        return {"mtime": mtime, "size": size, "fingerprint": h.hexdigest()}
    except Exception:
        return {"mtime": 0, "size": 0, "fingerprint": ""}

def index_chunk(actions):
    if not actions:
        return
    helpers.bulk(es, actions)

def scan_and_index():
    data = Path(DATA_FOLDER)
    to_index = []
    new_state_files = {}
    for p in data.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(data))
        try:
            fp = fingerprint_file(p)
        except Exception:
            continue
        prev = state["files"].get(rel)
        if (not prev) or (prev.get("fingerprint") != fp["fingerprint"]):
            if fp["size"] > 100*1024*1024:
                new_state_files[rel] = fp
                continue
            try:
                with p.open("r", errors="ignore", encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        text = line.strip()
                        if not text:
                            continue
                        doc = {
                            "_index": "osint-results",
                            "_source": {
                                "path": rel,
                                "abs_path": str(p),
                                "line": text,
                                "lineno": lineno,
                                "size": fp["size"],
                                "fingerprint": fp["fingerprint"],
                                "indexed_at": int(time.time())
                            }
                        }
                        to_index.append(doc)
                        if len(to_index) >= BULK_CHUNK:
                            index_chunk(to_index)
                            to_index = []
            except Exception:
                pass
        new_state_files[rel] = fp
    if to_index:
        index_chunk(to_index)
    state["files"] = new_state_files
    state["last_indexed"] = int(time.time())
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass

@app.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "")
    size = int(request.args.get("size", 50))
    if not q:
        return jsonify({"error": "missing q parameter"}), 400
    body = {
        "query": {
            "match_phrase": {
                "line": q
            }
        },
        "size": size,
        "sort": [{"indexed_at": {"order": "desc"}}]
    }
    res = es.search(index="osint-results", body=body)
    hits = []
    for h in res.get("hits", {}).get("hits", []):
        s = h["_source"]
        hits.append({
            "path": s.get("path"),
            "abs_path": s.get("abs_path"),
            "line": s.get("line"),
            "lineno": s.get("lineno"),
            "score": h.get("_score"),
        })
    return jsonify({"total": res.get("hits", {}).get("total", {}), "hits": hits})

def background_loop():
    try:
        scan_and_index()
    except Exception as e:
        print("Initial scan error:", e)
    while True:
        try:
            scan_and_index()
        except Exception as e:
            print("Scan error:", e)
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    import threading
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)
