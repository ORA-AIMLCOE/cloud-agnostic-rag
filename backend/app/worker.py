import re
import shutil
import threading
import time

from app.astra import Astra
from app.github import GitHub, publishing_safe
from app.recipe import assert_boundaries, generate_recipe, inspect_source, model_context
from app.security import SafeError
from app.validation import apply_model_patch, diff_report, run_sandbox


class Worker:
    def __init__(self, store, settings, github_factory=GitHub, astra_factory=Astra, validator=run_sandbox):
        self.store, self.settings = store, settings
        self.github_factory, self.astra_factory, self.validator = github_factory, astra_factory, validator
        self.stop = threading.Event()
        self.thread = None
        self.lock_file = None

    def directory(self, identifier):
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise SafeError("Invalid job identifier.")
        root = self.settings.workspace_dir.resolve()
        directory = (root / identifier).resolve()
        if directory.parent != root:
            raise SafeError("Invalid workspace path.")
        return directory

    def start(self):
        # One worker owns this SQLite queue. A second server must not recover live jobs.
        self.lock_file = (self.settings.state_dir / "worker.lock").open("a+b")
        self.lock_file.seek(0)
        if not self.lock_file.read(1):
            self.lock_file.write(b"0")
            self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            import os

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("Another converter worker already owns this state directory.") from exc
        self.store.recover()
        self.thread = threading.Thread(target=self.loop, name="conversion-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.lock_file and (not self.thread or not self.thread.is_alive()):
            self.lock_file.close()
            self.lock_file = None

    def cancelled(self, identifier):
        return self.stop.is_set() or self.store.get(identifier)["cancel_requested"]

    def check_cancel(self, identifier):
        if self.cancelled(identifier):
            raise SafeError("Conversion cancelled before publication.")

    def loop(self):
        while not self.stop.is_set():
            self.cleanup()
            claim = self.store.claim()
            if claim:
                self.process(*claim)
            else:
                self.stop.wait(1)

    def cleanup(self):
        with self.store.lock:
            for identifier in self.store.expire(time.time() - self.settings.job_retention_hours * 3600):
                directory = self.directory(identifier)
                if directory.exists():
                    shutil.rmtree(directory)

    def process(self, identifier, operation):
        github = None
        try:
            job = self.store.get(identifier)
            secrets = self.store.secrets(identifier)
            github = self.github_factory(job["repository_url"], secrets["github_token"])
            if operation == "queued_inspection":
                self.store.update(identifier, phase="Reading the source branch")
                sha, tree, files = github.snapshot(job["source_branch"])
                self.check_cancel(identifier)
                analysis = inspect_source(files)
                source = self.directory(identifier) / "source"
                for name, content in files.items():
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                safe = publishing_safe(files)
                self.store.update(
                    identifier,
                    status="ready",
                    phase="Repository inspected. Complete the OCI settings.",
                    source_sha=sha,
                    source_tree=tree,
                    analysis=analysis,
                    publish_allowed=safe,
                    checks=[
                        {"name": "Supported project structure", "status": "passed"},
                        {"name": "Source credential scan", "status": "passed"},
                        {"name": "Branch-triggered workflows", "status": "passed" if safe else "blocked"},
                    ],
                )
                return
            self.check_cancel(identifier)
            source = self.directory(identifier) / "source"
            files = {
                p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()
            }
            target = secrets["target"]
            changes = generate_recipe(files)
            self.store.update(identifier, phase="Preparing OCI adapters and configuration")
            astra = self.astra_factory(self.settings)
            failure = ""
            usage = []
            success = False
            for attempt in range(self.settings.astra_max_attempts):
                self.check_cancel(identifier)
                self.store.update(identifier, phase=f"OCI Astra: adapter review {attempt + 1}")
                patch, tokens = astra.refine(model_context(files, changes, target, failure))
                usage.append(tokens)
                changes = apply_model_patch(changes, patch)
                assert_boundaries(files, changes)
                self.check_cancel(identifier)
                self.store.update(
                    identifier, phase="Running isolated application and adapter tests", model_usage=usage
                )
                output = self.directory(identifier) / "output"
                for name, content in files.items():
                    path = output / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                for name, content in changes.items():
                    path = output / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8", newline="")
                success, log = self.validator(
                    output, self.settings.validator_image, identifier, lambda: self.cancelled(identifier)
                )
                self.check_cancel(identifier)
                failure = log[-12000:]
                if success:
                    break
            report = diff_report(files, changes)
            # Never treat model statements as test evidence; only the validator determines status.
            checks = [
                {"name": "Core RAG files unchanged", "status": "passed"},
                {"name": "Build and offline tests", "status": "passed" if success else "failed"},
                {"name": "Live OCI access and RAG", "status": "not_run"},
            ]
            self.store.update(
                identifier,
                files=report,
                checks=checks,
                validation_log=failure,
                metrics={
                    "modified": sum(f["kind"] == "modified" for f in report),
                    "added": sum(f["kind"] == "added" for f in report),
                    "core_unchanged": job["analysis"]["protected_files"],
                },
            )
            if not success:
                raise SafeError("Offline validation failed. Review test results; no branch was published.")
            self.check_cancel(identifier)
            self.store.update(identifier, phase="Summarizing file changes with GPT Astra")
            descriptions, description_usage = astra.describe_changes(report)
            self.check_cancel(identifier)
            for entry in report:
                entry["reason"] = descriptions[entry["path"]]
                entry["reason_source"] = "astra"
            self.store.update(identifier, files=report, description_usage=description_usage)
            if secrets.get("publish"):
                if not publishing_safe(files):
                    raise SafeError(
                        "Automatic branch workflows could deploy code. Limit push workflows to main before enabling publication, or generate without publishing."
                    )
                branch = "migration/oci-" + identifier[:12]
                self.store.update(identifier, phase="Creating the OCI commit", target_branch=branch)
                commit = github.prepare_commit(
                    job["source_sha"], job["source_tree"], {f["path"]: changes[f["path"]] for f in report}
                )
                self.store.update(identifier, target_commit=commit)
                self.check_cancel(identifier)
                url = github.publish(branch, commit)
                self.store.update(
                    identifier,
                    branch_url=url,
                    compare_url=job["repository_url"] + "/compare/" + job["source_sha"] + "..." + commit,
                )
            self.store.update(
                identifier,
                status="completed",
                phase="OCI code validated"
                + (" and branch published" if secrets.get("publish") else "; ready to download"),
            )
        except SafeError as exc:
            status = "cancelled" if self.cancelled(identifier) else "failed"
            self.store.update(identifier, status=status, phase=str(exc))
        except Exception as exc:  # noqa: BLE001 - job boundary must sanitize every failure
            self.store.update(
                identifier,
                status="failed",
                phase="Conversion stopped safely. No success is claimed; check configuration and retry.",
                error_type=type(exc).__name__,
            )
        finally:
            if github:
                github.close()
