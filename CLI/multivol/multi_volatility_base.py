"""Shared base class for Volatility runner classes."""

# pylint: disable=line-too-long,too-many-instance-attributes
import os
from dataclasses import dataclass
from typing import Any, Optional
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
