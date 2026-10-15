import os
import shutil
import subprocess
from pathlib import Path

root = Path("/tmp/project")
shutil.copytree("/source", root)
# Credentials and host environment are never mounted. Network is disabled by docker run.
env = dict(os.environ, AWS_EC2_METADATA_DISABLED="true", AWS_ACCESS_KEY_ID="testing",
           AWS_SECRET_ACCESS_KEY="testing", AWS_DEFAULT_REGION="ap-southeast-2", HOME="/tmp")
shutil.copytree("/opt/frontend/node_modules", root / "frontend/node_modules")
commands = [
    ("backend", ["python", "-m", "compileall", "-q", "app"]),
    ("backend", ["python", "-m", "pytest", "-q"]),
    ("frontend", ["node", "node_modules/typescript/bin/tsc", "-b"]),
    ("frontend", ["node", "node_modules/vite/bin/vite.js", "build"]),
    ("frontend", ["node", "node_modules/vitest/vitest.mjs", "run"]),
]
for cwd, command in commands:
    print("CHECK:", cwd, " ".join(command), flush=True)
    result = subprocess.run(command, cwd=root / cwd, env=env, timeout=180)
    if result.returncode:
        raise SystemExit(result.returncode)
print("All offline checks passed. Live OCI verification was not run.", flush=True)
