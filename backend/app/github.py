import base64
import io
import re
import stat
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

import httpx
import yaml

from app.security import SafeError, check_source_secrets

MAX_ARCHIVE = 20 * 1024 * 1024


class GitHub:
    def __init__(self, url, token, transport=None):
        self.slug = urlsplit(url).path.strip("/")
        self.client = httpx.Client(
            base_url="https://api.github.com",
            timeout=60,
            transport=transport,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def close(self):
        self.client.close()

    def _send(self, method, path, **kwargs):
        try:
            response = self.client.request(method, "/repos/" + self.slug + path, **kwargs)
        except httpx.TimeoutException:
            raise SafeError("GitHub connection timed out. Check your network or proxy and retry inspection.") from None
        except httpx.RequestError:
            raise SafeError("Could not connect to GitHub. Check your network or proxy and retry inspection.") from None
        if response.status_code >= 400:
            if response.status_code == 401:
                raise SafeError("GitHub rejected the token (401). Check that it is correct, unexpired and not revoked.")
            if response.status_code in {403, 429} and (
                response.headers.get("x-ratelimit-remaining") == "0"
                or response.headers.get("retry-after")
                or response.status_code == 429
            ):
                raise SafeError("GitHub rate limit reached. Wait before retrying inspection.")
            if response.status_code == 403 and response.headers.get("x-github-sso"):
                raise SafeError("GitHub requires organization SSO authorization for this token (403).")
            if response.status_code == 403 and "contents=" in response.headers.get("x-accepted-github-permissions", ""):
                raise SafeError(
                    "GitHub denied repository Contents access (403). In your fine-grained token, select the repository owner and this repository, "
                    "set Repository permissions > Contents to Read and write, and save. If organization approval is required, wait for approval, then retry inspection."
                )
            if response.status_code == 404:
                raise SafeError(
                    "GitHub could not find or grant access to the repository or source branch (404). "
                    "Check the URL, branch name, token repository selection and organization approval."
                )
            raise SafeError(
                f"GitHub request failed ({response.status_code}). Check repository access, branch rules, and token permissions."
            )
        return response

    def request(self, method, path, **kwargs):
        return self._send(method, path, **kwargs).json()

    def snapshot(self, branch):
        commit = self.request("GET", "/commits/" + quote(branch, safe=""))
        sha = commit["sha"]
        response = self._send("GET", f"/zipball/{sha}", follow_redirects=False)
        if response.status_code != 302:
            raise SafeError("GitHub did not return a source archive.")
        location = response.headers.get("location", "")
        parsed = urlsplit(location)
        if parsed.scheme != "https" or parsed.hostname != "codeload.github.com":
            raise SafeError("GitHub returned an unexpected archive location.")
        data = bytearray()
        # Never forward GitHub credentials to a redirect destination.
        with httpx.stream("GET", location, timeout=90, follow_redirects=False) as archive:
            if archive.status_code != 200:
                raise SafeError("Could not download the source archive.")
            for chunk in archive.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_ARCHIVE:
                    raise SafeError("Repository archive exceeds the 20 MB demo limit.")
        files = unpack_archive(bytes(data))
        check_source_secrets({p: v.decode("utf-8", errors="replace") for p, v in files.items()})
        return sha, commit["commit"]["tree"]["sha"], files

    def prepare_commit(self, base_sha, base_tree, changes):
        entries = []
        for path, content in sorted(changes.items()):
            blob = self.request(
                "POST",
                "/git/blobs",
                json={"content": base64.b64encode(content.encode()).decode(), "encoding": "base64"},
            )
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self.request("POST", "/git/trees", json={"base_tree": base_tree, "tree": entries})
        commit = self.request(
            "POST",
            "/git/commits",
            json={
                "message": "Add OCI providers and configuration for aws_rag",
                "tree": tree["sha"],
                "parents": [base_sha],
            },
        )
        return commit["sha"]

    def publish(self, branch, commit_sha):
        self.request("POST", "/git/refs", json={"ref": "refs/heads/" + branch, "sha": commit_sha})
        return f"https://github.com/{self.slug}/tree/{quote(branch, safe='/')}"


def unpack_archive(data):
    files, total = {}, 0
    normalized_paths = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 3000:
            raise SafeError("Repository has too many entries for this project-specific converter.")
        for item in archive.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir():
                continue
            if (
                item.filename.startswith("/")
                or len(parts) < 2
                or any(p in {"..", "."} for p in parts)
                or "\\" in item.filename
            ):
                raise SafeError("Unsafe path in repository archive.")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise SafeError("Symlinks are not supported in conversion snapshots.")
            path = "/".join(parts[1:])
            if any(p in {".git", ".state", ".workspaces", "node_modules", ".venv"} for p in parts):
                raise SafeError("Repository contains generated or private runtime directories.")
            if PurePosixPath(path).name in {".env", ".env.local", ".env.production"}:
                raise SafeError("Remove committed environment secrets before conversion.")
            total += item.file_size
            if total > MAX_ARCHIVE or item.file_size > 2 * 1024 * 1024:
                raise SafeError("Expanded repository exceeds the demo size limit.")
            if path.casefold() in normalized_paths or not re.fullmatch(r"[A-Za-z0-9_./@ +()-]+", path):
                raise SafeError("Unsupported or duplicate repository path.")
            normalized_paths.add(path.casefold())
            files[path] = archive.read(item)
    return files


def publishing_safe(files):
    # Branch creation can trigger Actions. This version publishes only when the source has
    # no push/create triggers, or push is explicitly limited to main/master.
    for path, data in files.items():
        if not path.startswith(".github/workflows/") or not path.endswith((".yml", ".yaml")):
            continue
        try:
            workflow = yaml.safe_load(data)
            events = workflow.get("on", workflow.get(True, {}))
            if isinstance(events, str):
                events = {events: None}
            if isinstance(events, list):
                events = dict.fromkeys(events)
            if "create" in events:
                return False
            if "push" in events:
                config = events["push"]
                if not isinstance(config, dict):
                    return False
                branches = config.get("branches", [])
                if not branches or any(b not in {"main", "master"} for b in branches):
                    return False
        except (yaml.YAMLError, AttributeError, TypeError):
            return False
    return True
