import subprocess
import sys
from pathlib import Path


def test_competitor_v1_proto_compiles(tmp_path: Path) -> None:
    repository_root = Path(__file__).parents[3]
    proto_root = repository_root / "packages/contracts/proto"
    proto_file = proto_root / "distributed_agent_contracts/competitor/v1/competitor.proto"
    descriptor = tmp_path / "competitor-v1.pb"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={proto_root}",
            f"--descriptor_set_out={descriptor}",
            str(proto_file),
        ],
        check=True,
    )

    assert descriptor.exists()
