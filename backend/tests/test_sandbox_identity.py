from types import SimpleNamespace

import pytest

from app import validation


@pytest.mark.parametrize(
    "host_uid,host_gid,expected",
    [(1001, 1002, (1001, 1002)), (None, None, (1000, 1000)), (0, 0, (1000, 1000))],
)
def test_sandbox_matches_owner_and_keeps_isolation(monkeypatch, tmp_path, host_uid, host_gid, expected):
    host = SimpleNamespace()
    if host_uid is not None:
        host.geteuid = lambda: host_uid
        host.getegid = lambda: host_gid
    monkeypatch.setattr(validation, "os", host)
    monkeypatch.setattr(validation.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    commands = []

    def launch(command, stdout, stderr):
        commands.append(command)
        stdout.write(b"Offline checks passed")
        return SimpleNamespace(poll=lambda: 0, returncode=0)

    monkeypatch.setattr(validation.subprocess, "Popen", launch)
    workspace = tmp_path / "output"
    workspace.mkdir(mode=0o700)
    passed, log = validation.run_sandbox(workspace, "validator:test", "job1", lambda: False)
    assert passed and log == "Offline checks passed"
    command = commands[0]
    uid, gid = expected
    assert command[command.index("--user") + 1] == f"{uid}:{gid}"
    assert f"uid={uid},gid={gid}" in command[command.index("--tmpfs") + 1]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges"
    assert command[command.index("--mount") + 1].endswith("target=/source,readonly")
