"""Volatility 3 memory analysis orchestration using Docker containers."""

# pylint: disable=line-too-long
import json
import logging
import os
import re
import uuid
import docker
from multivol.multi_volatility_base import MultiVolatilityBase, Vol3RunConfig


class MultiVolatility3(MultiVolatilityBase):
    """Orchestrate Volatility 3 commands executed inside Docker containers."""

    def execute_command_volatility3(
        self, command: str, config: Vol3RunConfig, quiet: bool = False, lock=None
    ) -> tuple[str, bool]:  # pylint: disable=too-many-return-statements,too-many-branches,too-many-locals,too-many-statements
        """Execute a Volatility 3 command in Docker and handle output."""
        if not quiet:
            self.safe_print(f"[+] Starting {command}...", lock)

        client = docker.from_env()

        # Resolve paths for DooD
        host_symbols_path = self.resolve_path(
            os.path.abspath(config.symbols_path), config.host_path
        )
        host_cache_path = self.resolve_path(os.path.abspath(config.cache_dir), config.host_path)
        host_plugin_dir = self.resolve_path(os.path.abspath(config.plugin_dir), config.host_path)
        host_output_dir = self.resolve_path(os.path.abspath(config.output_dir), config.host_path)

        host_dump_path = self.resolve_path(os.path.abspath(config.dump_dir), config.host_path)
        host_dump_dir = os.path.dirname(host_dump_path)

        # Debug logging for path resolution
        if config.show_commands:
            print(f"[DEBUG] dump={config.dump}, dump_dir={config.dump_dir}", flush=True)
            print(
                f"[DEBUG] host_dump_path={host_dump_path}, host_dump_dir={host_dump_dir}",
                flush=True,
            )

        volumes = {
            host_dump_dir: {"bind": "/dump_dir", "mode": "ro"},
            host_symbols_path: {"bind": "/symbols", "mode": "rw"},
            host_cache_path: {"bind": "/root/.cache/volatility3", "mode": "rw"},
            host_plugin_dir: {"bind": "/plugins", "mode": "ro"},
            host_output_dir: {"bind": "/output", "mode": "rw"},
        }

        # Base arguments
        # Base arguments with new volume paths:
        # dump_dir -> /dump_dir
        # symbols -> /symbols
        # cache -> /root/.cache/volatility3
        # plugins -> /plugins

        # NOTE: -f expects the file path. Volume maps dump_dir to /dump_dir.
        # So dump file is at /dump_dir/basename(dump)
        dump_filename = os.path.basename(config.dump)
        if config.show_commands:
            print(
                f"[DEBUG] dump_filename={dump_filename}, full path in container=/dump_dir/{dump_filename}",
                flush=True,
            )
        base_args = f"vol -q -f /dump_dir/{dump_filename} -o /output -s /symbols -p /plugins"

        if config.custom_symbol:
            if config.show_commands:
                print(
                    f"[DEBUG] Custom Symbol Selected: {config.custom_symbol}",
                    flush=True,
                )

        if config.fetch_symbols:
            base_args = f"{base_args} --remote-isf-url https://github.com/Abyss-W4tcher/volatility3-symbols/raw/master/banners/banners.json"

        if config.format == "json":
            output_file = os.path.join(config.output_dir, f"{command}_output.json")
            output_filename = f"{command}_output.json"
            cmd_args = f"{base_args} -r json {command} {config.extra_args}"
        else:
            output_file = os.path.join(config.output_dir, f"{command}_output.txt")
            output_filename = f"{command}_output.txt"
            cmd_args = f"{base_args} {command} {config.extra_args}"

        # Redirect output to file inside container (avoids Docker log rotation issues)
        cmd_with_redirect = f"/bin/sh -c '{cmd_args} > /output/{output_filename} 2>&1'"

        if config.show_commands:
            print(
                f"[DEBUG] output_dir={config.output_dir}, output_file={output_file}",
                flush=True,
            )
            print(
                f"[DEBUG] output_dir exists: {os.path.exists(config.output_dir)}",
                flush=True,
            )
            print(f"[DEBUG] Volatility 3 Command: {cmd_args}", flush=True)
            print(f"[DEBUG] Docker Volumes: {json.dumps(volumes, indent=2)}", flush=True)

        try:
            # Sanitize command name for Docker container name
            # Use scan_id for predictable naming so API can track container status
            sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "", command)
            if config.scan_id:
                container_name = f"vol3_{config.scan_id[:8]}_{sanitized_name}"
            else:
                container_name = f"vol3_{sanitized_name}_{str(uuid.uuid4())[:8]}"

            # Remove existing container if it exists (fix for 409 Conflict)
            if config.show_commands:
                print(
                    f"[DEBUG] Removing existing container: {container_name}",
                    flush=True,
                )
            self._cleanup_existing_container(client, container_name, lock)

            container = self._run_detached_container(
                client, config.docker_image, cmd_with_redirect, volumes, name=container_name
            )

            # Wait for container to finish (output is written to file, not logs)
            wait_result = container.wait()
            exit_code = wait_result.get("StatusCode", 0)
            # Don't remove container - API will check status and clean up

            if config.format == "json":
                self._trim_output_file(output_file, command, start=2)

        except Exception as e:  # pylint: disable=broad-except
            self.safe_print(f"[!] Error running {command}: {e}", lock)
            logging.exception("Volatility3 container failed for %s", command)
            return (command, False)

        if not quiet:
            self.safe_print(f"[+] {command} finished.", lock)

        if exit_code != 0:
            return (command, False)

        try:
            with open(output_file, "r", encoding="utf-8") as f:
                content = f.read()

            if (
                "Volatility experienced" in content
                or "vol.py: error:" in content
                or "vol: error:" in content
            ):
                return (command, False)
            if config.format == "json":
                start_index = content.find("[")
                if start_index == -1:
                    start_index = content.find("{")

                if start_index != -1:
                    json.loads(content[start_index:])
                    return (command, True)
                lines = content.splitlines()
                if len(lines) > 1:
                    json.loads("\n".join(lines[1:]))
                    return (command, True)
                return (command, False)
            return (command, True)
        except Exception as e:  # pylint: disable=broad-except
            logging.warning("Could not validate output for %s: %s", command, e)
            return (command, False)

    def get_commands(self, opsys: str) -> list[str]:
        """Return the list of plugin commands for the given operating system."""
        return self._load_commands_yaml("vol3", opsys)
