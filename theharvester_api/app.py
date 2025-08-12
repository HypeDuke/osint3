import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/harvest", methods=["GET"])
def harvest():
    domain = request.args.get("domain")
    source = request.args.get("source", "google")
    limit = request.args.get("limit", "100")

    if not domain:
        return jsonify({"error": "Missing 'domain' parameter"}), 400

    cmd = [
        "python3", "theHarvester/theHarvester.py",
        "-d", domain,
        "-l", limit,
        "-b", source
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return jsonify({"domain": domain, "source": source, "output": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e), "stderr": e.stderr}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100)
