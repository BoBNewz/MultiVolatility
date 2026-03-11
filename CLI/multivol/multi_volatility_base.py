"""Shared base class for Volatility runner classes."""
import os
from dataclasses import dataclass, field
from typing import Optional
from rich import print as rprint


@dataclass
class Vol3RunConfig:
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


@dataclass
class Vol2RunConfig:
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

    def resolve_path(self, path: str, host_path: str | None) -> str:
        """Translate a container-side path to the corresponding host path for Docker-in-Docker (DooD)."""
        if host_path:
            if path.startswith("/storage"):
                rel_path = os.path.relpath(path, "/storage")
                return os.path.join(host_path, "storage", "data", rel_path)

            try:
                from api_server.config import BASE_DIR
                if path.startswith(BASE_DIR):
                    rel_path = os.path.relpath(path, BASE_DIR)
                    return os.path.join(host_path, rel_path)
            except ImportError:
                if path.startswith(os.getcwd()):
                    rel_path = os.path.relpath(path, os.getcwd())
                    return os.path.join(host_path, rel_path)
        return path

    def safe_print(self, message: str, lock) -> None:
        """Thread-safe print using rich."""
        if lock:
            with lock:
                rprint(message)
        else:
            rprint(message)
