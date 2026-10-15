import ast
import hashlib
import re
import subprocess
import time

from app.security import SafeError, has_secret

EDITABLE = {
    "backend/app/providers/oci/" + name
    for name in ("storage.py", "llm.py", "ingestion.py", "vector_search.py", "embeddings.py")
}


def apply_model_patch(files, patch):
    updated = dict(files)
    seen = set()
    for item in patch["files"]:
        if not isinstance(item, dict):
            raise SafeError("Astra returned an invalid file change.")
        path, content = item.get("path"), item.get("content")
        if path not in EDITABLE or path in seen or not isinstance(content, str) or len(content) > 60000:
            raise SafeError("Astra attempted a change outside the permitted adapter files.")
        if has_secret(content):
            raise SafeError("Generated code contains a possible credential; publication blocked.")
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise SafeError("An OCI adapter contains invalid Python syntax.") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(
                    n.split(".")[0]
                    not in {
                        "app",
                        "json",
                        "hashlib",
                        "math",
                        "time",
                        "logging",
                        "contextlib",
                        "uuid",
                        "oci",
                        "sqlalchemy",
                        "array",
                        "requests",
                        "typing",
                    }
                    for n in names
                ):
                    raise SafeError("Astra introduced an unsupported import.")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec", "compile", "__import__", "open"}
            ):
                raise SafeError("Astra introduced an unsupported execution operation.")
        if re.search(r"https?://", content):
            raise SafeError("Adapter endpoints must come from configuration, not generated URLs.")
        seen.add(path)
        updated[path] = content
    return updated


def reason_for(path):
    reasons = {
        "storage.py": "Replace S3 operations with OCI Object Storage while preserving document keys and metadata.",
        "llm.py": "Call the selected OCI answer model and normalize its response for the unchanged RAG workflow.",
        "embeddings.py": "Generate document and query embeddings with the separately selected model and validate vector dimensions.",
        "ingestion.py": "Reuse PDF extraction, chunk text, and persist embeddings idempotently in the OCI vector tables.",
        "vector_search.py": "Retrieve source text with cosine search and strict document, owner and model-index filters.",
        "common.py": "Centralize OCI authentication, sanitized provider errors and model-index identity.",
        "settings.py": "Validate OCI endpoints, independent model settings and chunking configuration.",
    }
    if path in {"backend/app/providers/oci/database.py", "backend/app/providers/oci/database_models.py",
                "backend/app/providers/oci/database_types.py", "backend/app/providers/oci/repository.py"}:
        return "Persist metadata and chat history in Autonomous Database through an Oracle adapter, preserving repository contracts and the source AWS schema."
    if path.startswith("backend/app/providers/oci/"):
        return reasons.get(
            path.rsplit("/", 1)[-1], "Construct OCI adapters behind the existing provider interfaces."
        )
    if path == "backend/app/providers/factory.py":
        return "Activate the OCI provider branch while preserving the existing AWS factory."
    if path.startswith("backend/app/core/"):
        return "Select OCI object-prefix and Oracle persistence adapters; existing AWS wiring remains compatible."
    if path.endswith("test_contracts.py"):
        return "Replace the former OCI-not-implemented assertion with invalid-configuration validation. Existing AWS tests remain intact."
    if "/tests/" in path:
        return "Add offline OCI tests for dimensions, source mapping, document filtering and chunking."
    if path == "scripts/check_oci_database.py":
        return "Verify live Oracle connectivity, cosine ranking and document isolation using rolled-back probe writes."
    if path.startswith("scripts/"):
        return "Initialize Oracle metadata, history and native vector tables explicitly in the target application schema."
    if "requirements" in path:
        return "Add pinned OCI SDK dependencies on top of the original application dependency lock."
    if path.startswith("docs/"):
        return "Explain setup, the migration boundaries and live verification that remains to be performed."
    if path.startswith(".env"):
        return "Provide a credential-free OCI configuration template; real values are downloaded separately."
    return "Exclude OCI runtime credentials from version control."


def diff_report(original, changes):
    import difflib

    result = []
    for path, text in sorted(changes.items()):
        before = original.get(path, b"").decode("utf-8")
        if before == text:
            continue
        diff = list(
            difflib.unified_diff(
                before.splitlines(), text.splitlines(), fromfile="a/" + path, tofile="b/" + path, lineterm=""
            )
        )
        result.append(
            {
                "path": path,
                "reason": reason_for(path),
                "kind": "modified" if path in original else "added",
                "added": sum(l.startswith("+") and not l.startswith("+++") for l in diff),
                "removed": sum(l.startswith("-") and not l.startswith("---") for l in diff),
                "diff": "\n".join(diff),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    return result


def run_sandbox(workspace, image, job_id, cancelled):
    if not re.fullmatch(r"[a-zA-Z0-9_./:-]+", image):
        raise SafeError("Invalid validator image configuration.")
    try:
        check = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafeError(
            "Docker validation is unavailable. Start Docker and run scripts/prepare-validation.ps1."
        ) from exc
    if check.returncode:
        raise SafeError("Validation image is missing. Run scripts/prepare-validation.ps1 before converting.")
    name = "oci-convert-" + job_id
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--user",
        "1000:1000",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=1g,uid=1000,gid=1000",
        "--mount",
        f"type=bind,source={workspace.resolve()},target=/source,readonly",
        image,
    ]
    log_path = workspace.parent / "validation.log"
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            start = time.monotonic()
            while process.poll() is None:
                if cancelled() or time.monotonic() - start > 300 or log_path.stat().st_size > 1_000_000:
                    subprocess.run(["docker", "kill", name], capture_output=True, timeout=20, check=False)
                    process.kill()
                    process.wait()
                    raise SafeError("Validation was cancelled or exceeded its resource limit.")
                time.sleep(0.3)
        output = log_path.read_text(errors="replace")[-16000:]
        return process.returncode == 0, output
    except OSError as exc:
        raise SafeError("Could not start isolated validation.") from exc
