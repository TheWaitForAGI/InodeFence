"""Execute an explicit JSON config through the safe Python reference only."""

import argparse
from pathlib import Path

from inodefence.campaign_export import export_campaign
from inodefence.experiment_config import ExperimentConfig, run_configured_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.targets import PythonTarfileTarget


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    config = ExperimentConfig.from_json(args.config.read_text())
    if config.target.target_id != "python-tarfile-data" or config.target.timeout_seconds is None:
        raise ValueError("this CLI supports timed Python reference campaigns only")
    result = run_configured_campaign(
        config, minimal_seed_corpus(), PythonTarfileTarget(config.target.timeout_seconds)
    )
    manifest, _ = export_campaign(result, args.output)
    # Serialize the same immutable config read before execution, never RunResult.
    (args.output / "experiment.json").write_text(config.to_json() + "\n", encoding="ascii")
    print(f"config_id={config.config_id} executions={len(result.steps)} manifest={manifest}")


if __name__ == "__main__":
    main()
