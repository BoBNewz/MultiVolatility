# multi_volatility2.py
# Implements Volatility2 memory analysis orchestration, Docker command generation, and backend communication.
import time
import os
import json
import logging
import re
import yaml
import docker
from multivol.multi_volatility_base import MultiVolatilityBase, Vol2RunConfig

class MultiVolatility2(MultiVolatilityBase):
    def _output_file_info(self, command: str, output_dir: str, fmt: str) -> tuple[str, str]:
        """Return (output_file_path, output_filename) for the given command and format."""
        ext = "json" if fmt == "json" else "txt"
        filename = f"{command}_output.{ext}"
        return os.path.join(output_dir, filename), filename

    def _trim_json_output(self, output_file: str, command: str) -> None:
        """Keep only the last line of a JSON output file (avoids log-rotation noise)."""
        try:
            with open(output_file, "r") as f:
                lines = f.readlines()
            if lines:
                with open(output_file, "w") as f:
                    f.writelines(lines[-1])
        except OSError:
            logging.warning("Could not trim JSON output for %s", command, exc_info=True)

    def execute_command_volatility2(self, command: str, config: Vol2RunConfig, quiet: bool = False, lock=None) -> tuple[str, bool]:
        # Executes a Volatility2 command in Docker and handles output
        if not quiet:
            self.safe_print(f"[+] Starting {command}...", lock)

        client = docker.from_env()

        host_profiles_path = self.resolve_path(os.path.abspath(config.profiles_path), config.host_path)
        host_dump_path_src = self.resolve_path(os.path.abspath(config.dump_file_path), config.host_path)
        host_output_dir = self.resolve_path(os.path.abspath(config.output_dir), config.host_path)

        volumes = {
            host_dump_path_src: {'bind': f'/dumps/{config.dump}', 'mode': 'rw'},
            host_profiles_path: {'bind': '/home/vol/profiles', 'mode': 'rw'},
            host_output_dir: {'bind': '/output', 'mode': 'rw'},
        }

        cmd_args = f"--plugins=/home/vol/profiles -f /dumps/{config.dump} --profile={config.profile} --output={config.format} {command}"
        if config.show_commands:
            print(f"[DEBUG] Volatility 2 Command: vol.py {cmd_args}", flush=True)

        output_file, output_filename = self._output_file_info(command, config.output_dir, config.format)
        cmd_with_redirect = f"/bin/sh -c 'vol.py {cmd_args} > /output/{output_filename} 2>&1'"

        sanitized_name = re.sub(r'[^a-zA-Z0-9_.-]', '', command)
        scan_id = os.path.basename(os.path.normpath(config.output_dir))
        container_name = f"vol2_{scan_id[:8]}_{sanitized_name}"

        try:
            existing = client.containers.get(container_name)
            existing.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception as e:
            self.safe_print(f"[!] Warning: Failed to cleanup existing container {container_name}: {e}", lock)
            logging.warning("Failed to cleanup existing container %s", container_name, exc_info=True)

        try:
            container = client.containers.run(
                image=config.docker_image,
                name=container_name,
                command=cmd_with_redirect,
                volumes=volumes,
                tty=False,
                remove=False,
                detach=True,
                log_config={"type": "none"},
            )
            container.wait()
        except Exception as e:
            self.safe_print(f"[!] Error running {command}: {e}", lock)
            logging.exception("Volatility2 container failed for %s", command)
            return (command, False)

        time.sleep(0.5)
        if config.format == "json":
            self._trim_json_output(output_file, command)

        if not quiet:
            self.safe_print(f"[+] {command} finished.", lock)
        return (command, True)

    def get_commands(self, opsys: str) -> list[str]:

        base_dir = os.path.dirname(os.path.abspath(__file__))

        yaml_path = os.path.join(base_dir, "plugins_list", f"vol2_{opsys}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"File not found : {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

            modules_list = data["modules"]

            return modules_list
