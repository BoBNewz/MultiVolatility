import docker
import os
import logging
from typing import Any
from multivol.multi_volatility_base import MultiVolatilityBase


def get_strings(dump: str, dump_dir: str, output_dir: str, docker_image: str, lock: Any = False, host_path: str | None = None) -> None:
    base = MultiVolatilityBase()
    output_file = os.path.join(output_dir, "strings_output.txt")
    host_output_dir = base.resolve_path(os.path.abspath(output_dir), host_path)

    host_dump_path = base.resolve_path(os.path.abspath(dump_dir), host_path)
    host_dump_dir = os.path.dirname(host_dump_path)

    volumes = {
        host_dump_dir: {'bind': '/dump_dir', 'mode': 'ro'},
        host_output_dir: {'bind': '/output', 'mode': 'rw'}
    }

    dump_filename = os.path.basename(dump)
    output_filename = "strings_output.txt"

    cmd_with_redirect = f"/bin/sh -c 'strings /dump_dir/{dump_filename} > /output/{output_filename} 2>&1'"

    client = docker.from_env()

    try:
        container = client.containers.run(
            image=docker_image,
            command=cmd_with_redirect,
            volumes=volumes,
            tty=False,
            detach=True,
            remove=False,
            log_config={"type": "none"}
        )

        container.wait()
        container.remove()

    except Exception as e:
        base.safe_print(f"[!] Error running strings: {e}", lock)
        logging.exception("strings container failed")