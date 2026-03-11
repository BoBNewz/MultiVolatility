"""Volatility 2 memory analysis orchestration using Docker containers."""

# pylint: disable=line-too-long
import logging
import os
import re
import time
import docker
from multivol.multi_volatility_base import MultiVolatilityBase, Vol2RunConfig


class MultiVolatility2(MultiVolatilityBase):
    """Orchestrate Volatility 2 commands executed inside Docker containers."""

    def _output_file_info(self, command: str, output_dir: str, fmt: str) -> tuple[str, str]:
        """Return (output_file_path, output_filename) for the given command and format."""
        ext = "json" if fmt == "json" else "txt"
        filename = f"{command}_output.{ext}"
        return os.path.join(output_dir, filename), filename

    def execute_command_volatility2(
        self, command: str, config: Vol2RunConfig, quiet: bool = False, lock=None
    ) -> tuple[str, bool]:  # pylint: disable=too-many-locals
        """Execute a Volatility 2 command in Docker and handle output."""
        if not quiet:
            self.safe_print(f"[+] Starting {command}...", lock)

        client = docker.from_env()

        host_profiles_path = self.resolve_path(
            os.path.abspath(config.profiles_path), config.host_path
        )
        host_dump_path_src = self.resolve_path(
            os.path.abspath(config.dump_file_path), config.host_path
        )
        host_output_dir = self.resolve_path(os.path.abspath(config.output_dir), config.host_path)

        volumes = {
            host_dump_path_src: {"bind": f"/dumps/{config.dump}", "mode": "rw"},
            host_profiles_path: {"bind": "/home/vol/profiles", "mode": "rw"},
            host_output_dir: {"bind": "/output", "mode": "rw"},
        }

        cmd_args = f"--plugins=/home/vol/profiles -f /dumps/{config.dump} --profile={config.profile} --output={config.format} {command}"
        if config.show_commands:
            print(f"[DEBUG] Volatility 2 Command: vol.py {cmd_args}", flush=True)

        output_file, output_filename = self._output_file_info(
            command, config.output_dir, config.format
        )
        cmd_with_redirect = f"/bin/sh -c 'vol.py {cmd_args} > /output/{output_filename} 2>&1'"

        sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "", command)
        scan_id = os.path.basename(os.path.normpath(config.output_dir))
        container_name = f"vol2_{scan_id[:8]}_{sanitized_name}"

        self._cleanup_existing_container(client, container_name, lock)

        try:
            container = self._run_detached_container(
                client, config.docker_image, cmd_with_redirect, volumes, name=container_name
            )
            container.wait()
        except Exception as e:  # pylint: disable=broad-except
            self.safe_print(f"[!] Error running {command}: {e}", lock)
            logging.exception("Volatility2 container failed for %s", command)
            return (command, False)

        time.sleep(0.5)
        if config.format == "json":
            self._trim_output_file(output_file, command, start=-1)

        if not quiet:
            self.safe_print(f"[+] {command} finished.", lock)
        return (command, True)

    def get_commands(self, opsys: str) -> list[str]:
        """Return the list of plugin commands for the given operating system."""
        return self._load_commands_yaml("vol2", opsys)
