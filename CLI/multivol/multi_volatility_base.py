"""Shared base class for Volatility runner classes."""

# pylint: disable=line-too-long,too-many-instance-attributes
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional
import docker
import yaml
from rich import print as rprint


@dataclass
class ApiScanConfig:
    """Typed configuration for a scan request received from the API."""

    dump: str
    mode: str  # "vol2" or "vol3"
    linux: bool
    windows: bool
    output_dir: str
    scan_id: str
    image: str
    profiles_path: str
    symbols_path: str
    cache_path: str
    plugins_dir: str
    format: str = "json"
    commands: Optional[str] = None
    light: bool = False
    full: bool = False
    profile: Optional[str] = None
    processes: Optional[int] = None
    host_path: Optional[str] = None
    debug: bool = True
    fetch_symbol: bool = False
    custom_symbol: Optional[str] = None


@dataclass  # pylint: disable=too-many-instance-attributes
class Vol3RunConfig:
    """Configuration for a Volatility 3 run."""

    dump: str
    dump_dir: str
    symbols_path: str
    docker_image: str
    cache_dir: str
    plugin_dir: str
    output_dir: str
    format: str
    host_path: Optional[str] = None
    fetch_symbols: bool = False
    show_commands: bool = False
    custom_symbol: Optional[str] = None
    scan_id: Optional[str] = None
    extra_args: str = ""


@dataclass  # pylint: disable=too-many-instance-attributes
class Vol2RunConfig:
    """Configuration for a Volatility 2 run."""

    dump: str
    dump_file_path: str
    profiles_path: str
    docker_image: str
    profile: str
    output_dir: str
    format: str
    host_path: Optional[str] = None
    show_commands: bool = False


class MultiVolatilityBase:
    """Common functionality shared by multi_volatility2 and multi_volatility3."""

    def resolve_path(self, path: str, host_path: Optional[str]) -> str:
        """Translate a container-side path to the corresponding host path for Docker-in-Docker (DooD).

        Delegates to :func:`multivol.api_server.utils.resolve_host_path` when the
        API server package is importable; falls back to a lightweight local
        implementation for CLI-only usage where the server package is absent.
        """
        try:
            from multivol.api_server.utils import resolve_host_path  # pylint: disable=import-outside-toplevel

            return resolve_host_path(path, host_path_override=host_path)
        except ImportError:
            pass

        # Lightweight fallback for CLI-only context (no API server installed).
        if host_path:
            if path.startswith(os.getcwd()):
                rel_path = os.path.relpath(path, os.getcwd())
                return os.path.join(host_path, rel_path)
        return path

    def safe_print(self, message: str, lock: Any) -> None:
        """Thread-safe print using rich."""
        if lock:
            with lock:
                rprint(message)
        else:
            rprint(message)

    def _cleanup_existing_container(
        self, client: Any, container_name: str, lock: Any = None
    ) -> None:
        """Remove an existing Docker container by name, silently skipping if not found."""
        try:
            existing = client.containers.get(container_name)
            existing.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception as e:  # pylint: disable=broad-except
            self.safe_print(
                f"[!] Warning: Failed to cleanup existing container {container_name}: {e}",
                lock,
            )
            logging.warning(
                "Failed to cleanup existing container %s", container_name, exc_info=True
            )

    def run_detached_container(
        self,
        client: Any,
        image: str,
        command: str,
        volumes: dict,
        name: Optional[str] = None,
    ) -> Any:
        """Start a Docker container in detached mode and return the container object.

        Output is redirected to a file inside the container; Docker logging is disabled
        to avoid log-rotation issues.
        """
        run_kwargs: dict[str, Any] = {
            "image": image,
            "command": command,
            "volumes": volumes,
            "tty": False,
            "detach": True,
            "remove": False,
            "log_config": {"type": "none"},
        }
        if name is not None:
            run_kwargs["name"] = name
        return client.containers.run(**run_kwargs)

    def _trim_output_file(
        self, output_file: str, command: str, start: int = 0, end: Optional[int] = None
    ) -> None:
        """Rewrite *output_file* keeping only ``lines[start:end]``, in-place."""
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.writelines(lines[start:end])
        except OSError:
            logging.warning("Could not trim output for %s", command, exc_info=True)

    def _load_commands_yaml(self, vol_version: str, opsys: str) -> list[str]:
        """Load the plugin command list from the YAML file for *vol_version* and *opsys*."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.join(base_dir, "plugins_list", f"{vol_version}_{opsys}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"File not found : {yaml_path}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data["modules"]
