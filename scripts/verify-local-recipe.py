"""Developer smoke test against the explicitly supplied, trusted local aws_rag checkout.
Never used by the production worker; remote/model-produced code is tested only in Docker.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.github import unpack_archive
from app.recipe import generate_recipe, assert_boundaries
from app.validation import diff_report

if __name__ == "__main__":
    source = Path(sys.argv[1]).resolve()
    archive = subprocess.check_output(["git", "archive", "--format=zip", "--prefix=baseline/", "HEAD"], cwd=source)
    files = unpack_archive(archive)
    changes = generate_recipe(files)
    assert_boundaries(files, changes)
    output = ROOT / ".validation" / "recipe-smoke"
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for name, content in changes.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    report = diff_report(files, changes)
    (ROOT / ".validation" / "recipe-report.json").write_text(json.dumps(report, indent=2))
    env = dict(os.environ, PYTHONPATH=str(output / "backend"), AWS_EC2_METADATA_DISABLED="true", AWS_ACCESS_KEY_ID="testing", AWS_SECRET_ACCESS_KEY="testing", AWS_DEFAULT_REGION="ap-southeast-2")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=output / "backend", env=env, check=False)
    print("Generated files:", len(report), "Core source changes: 0")
    raise SystemExit(result.returncode)
