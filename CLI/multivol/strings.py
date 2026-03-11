import docker
import os
import logging
from multivol.multi_volatility_base import MultiVolatilityBase


def get_strings(dump, dump_dir, output_dir, docker_image, lock=False, host_path=None):
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
        logging.error(f"strings container failed: {e}", exc_info=True)