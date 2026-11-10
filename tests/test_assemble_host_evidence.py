import json

from scripts.assemble_host_evidence import main
from scripts.verify_host_freeze import digest


def test_assembly_preserves_inputs_and_refuses_overwrite(tmp_path, monkeypatch):
    argv = ["assemble", "--host-id", "HOST2"]
    for name in ("windows", "linux", "measured"):
        path = tmp_path / name
        path.write_text(json.dumps({name: "UNKNOWN"}))
        argv.extend((f"--{name}", str(path)))
    output = tmp_path / "output"
    argv.extend(("--output", str(output)))
    monkeypatch.setattr("sys.argv", argv)
    assert main() == 0
    content = output.read_bytes()
    result = json.loads(content)
    assert result["windows_inventory"] == {"windows": "UNKNOWN"}
    assert result["source_sha256"]["windows"] == digest((tmp_path / "windows").read_bytes())
    assert main() == 1
    assert output.read_bytes() == content
