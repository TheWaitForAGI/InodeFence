"""The inventory must not turn missing evidence into a Docker request."""

import json
from types import SimpleNamespace

from scripts import host_inventory_linux


def test_inventory_reports_unknown_docker_without_calling_it(monkeypatch, capsys):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout="ext4\n")

    def check_output(command, **kwargs):
        commands.append(command)
        if command[1:] == ["rev-parse", "HEAD"]:
            return "abc123\n"
        return ""

    monkeypatch.setattr(host_inventory_linux.subprocess, "run", run)
    monkeypatch.setattr(host_inventory_linux.subprocess, "check_output", check_output)
    host_inventory_linux.main()
    output = json.loads(capsys.readouterr().out)
    assert output["docker_engine"] is None
    assert output["image_id"] is None
    assert output["remaining_resources"] is None
    assert output["git_head"] == "abc123"
    assert output["git_dirty"] is False
    assert all(command[0] in {"findmnt", "git"} for command in commands)
