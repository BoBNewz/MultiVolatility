"""Entry point for MultiVolatility: orchestrate Volatility 2/3 analysis in parallel."""

# pylint: disable=line-too-long
import multiprocessing
import time
import os
import argparse
import sys
import logging
from datetime import datetime
from typing import Any, Union
import docker
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, SpinnerColumn, TextColumn

try:
    from .multi_volatility2 import MultiVolatility2
    from .multi_volatility3 import MultiVolatility3
    from .multi_volatility_base import Vol2RunConfig, Vol3RunConfig
    from .volatility_commands import get_strings
except ImportError:
    from multi_volatility2 import MultiVolatility2
    from multi_volatility3 import MultiVolatility3
    from multi_volatility_base import Vol2RunConfig, Vol3RunConfig
    from strings import get_strings


def vol3_wrapper(packed_args: Any) -> tuple[str, bool]:
    """Unpack arguments and call execute_command_volatility3."""
    instance, args = packed_args
    return instance.execute_command_volatility3(*args)


def vol2_wrapper(packed_args: Any) -> tuple[str, bool]:
    """Unpack arguments and call execute_command_volatility2."""
    instance, args = packed_args
    return instance.execute_command_volatility2(*args)


def _ensure_docker_image(image_name: str, console: Console) -> None:
    """Check that the Docker image is available locally, pulling it if needed."""
    try:
        client = docker.from_env()
        user_provided_image = "--image" in sys.argv
        try:
            client.images.get(image_name)
            if not user_provided_image:
                console.print(
                    f"[dim cyan][*] No --image provided, using default image: {image_name}[/dim cyan]"
                )
        except docker.errors.ImageNotFound:
            msg = (
                f"[*] Pulling image: {image_name}"
                if user_provided_image
                else f"[*] No --image provided, pulling default image: {image_name}"
            )
            with Progress(
                TextColumn("{task.description}"),
                SpinnerColumn("dots"),
                transient=True,
                console=console,
            ) as progress:
                progress.add_task(f"[bold green]{msg}[/bold green]", total=None)
                client.images.pull(image_name)
            console.print(f"[bold green]{msg}[/bold green]")
            console.print(f"[bold green][*] Image {image_name} ready.[/bold green]")
    except Exception as e:  # pylint: disable=broad-except
        console.print(f"[bold red]Warning: Docker check failed: {e}[/bold red]")
        logging.warning("Docker image check failed for %s", image_name, exc_info=True)


def _resolve_commands(
    arguments: argparse.Namespace,
) -> tuple[list[str], Union[MultiVolatility2, MultiVolatility3]]:
    """Return (commands, vol_instance) based on arguments.mode.

    Raises ValueError for unknown modes.
    """
    if arguments.mode == "vol2":
        instance = MultiVolatility2()
        if arguments.commands:
            cmds = arguments.commands.split(",")
        elif arguments.windows:
            cmds = instance.get_commands("windows.light" if arguments.light else "windows.full")
        elif arguments.linux:
            cmds = instance.get_commands("linux.light" if arguments.light else "linux.full")
        else:
            cmds = []
        return cmds, instance
    if arguments.mode == "vol3":
        instance = MultiVolatility3()
        if arguments.commands:
            cmds = arguments.commands.split(",")
        elif arguments.windows:
            cmds = instance.get_commands("windows.light" if arguments.light else "windows.full")
        elif arguments.linux:
            cmds = instance.get_commands("linux.light" if arguments.light else "linux.full")
        else:
            cmds = []
        return cmds, instance
    raise ValueError(f"Unknown mode: {arguments.mode!r}. Expected 'vol2' or 'vol3'.")


def _print_scan_summary(
    console: Console,
    successful_modules: list[str],
    failed_modules: list[str],
    arguments: argparse.Namespace,
) -> None:
    """Print success/failure counts and per-module status."""
    console.print(
        f"\n[bold green]Scan Complete![/bold green] "
        f"Success: {len(successful_modules)}, Failed: {len(failed_modules)}"
    )
    if successful_modules:
        console.print("\n[bold green]Successful Modules:[/bold green]")
        for mod in successful_modules:
            console.print(f"  - [green]{mod}[/green]")
    if failed_modules:
        console.print("\n[bold red]Failed Modules:[/bold red]")
        for mod in failed_modules:
            console.print(f"  - [red]{mod}[/red]")
            if arguments.format == "json":
                console.print(f"[red][!] Failed to validate JSON for {mod}[/red]")


def _run_vol2_pool(
    pool: Any,
    vol_instance: MultiVolatility2,
    commands: list[str],  # pylint: disable=too-many-arguments,too-many-positional-arguments
    arguments: argparse.Namespace,
    output_dir: str,
    lock: Any,
) -> tuple[list[str], list[str]]:
    """Run vol2 commands via pool and return (successful, failed) module lists."""
    vol2_cfg = Vol2RunConfig(
        dump=os.path.basename(arguments.dump),
        dump_file_path=os.path.abspath(arguments.dump),
        profiles_path=arguments.profiles_path,
        docker_image=arguments.image,
        profile=arguments.profile,
        output_dir=output_dir,
        format=arguments.format,
        host_path=arguments.host_path,
        show_commands=getattr(arguments, "debug", False),
    )
    tasks = [(vol_instance, (cmd, vol2_cfg, False, lock)) for cmd in commands]
    successful, failed = [], []
    for command_name, is_success in pool.imap_unordered(vol2_wrapper, tasks):
        (successful if is_success else failed).append(command_name)
    return successful, failed


def _run_vol3_pool(
    pool: Any,
    vol_instance: MultiVolatility3,
    commands: list[str],  # pylint: disable=too-many-arguments,too-many-positional-arguments
    arguments: argparse.Namespace,
    output_dir: str,
    lock: Any,
    console: Console,
) -> tuple[list[str], list[str]]:
    """Run vol3 commands via pool, including info bootstrap and strings, return (successful, failed)."""

    def _make_vol3_cfg() -> Vol3RunConfig:
        return Vol3RunConfig(
            dump=os.path.basename(arguments.dump),
            dump_dir=os.path.abspath(arguments.dump),
            symbols_path=arguments.symbols_path,
            docker_image=arguments.image,
            cache_dir=os.path.abspath(arguments.cache_path),
            plugin_dir=os.path.abspath(arguments.plugins_dir),
            output_dir=output_dir,
            format=arguments.format,
            host_path=arguments.host_path,
            fetch_symbols=getattr(arguments, "fetch_symbol", False),
            show_commands=getattr(arguments, "debug", False),
            custom_symbol=getattr(arguments, "custom_symbol", None),
            scan_id=getattr(arguments, "scan_id", None),
        )

    if arguments.windows or arguments.linux:
        info_module = "windows.info.Info" if arguments.windows else "linux.bash.Bash"
        if info_module in commands:
            commands.remove(info_module)
            vol_instance.execute_command_volatility3(info_module, _make_vol3_cfg(), False, lock)

    console.print("\n[+] Starting strings in background...")
    strings_future = pool.apply_async(
        get_strings,
        args=(
            os.path.basename(arguments.dump),
            os.path.abspath(arguments.dump),
            output_dir,
            arguments.image,
            lock,
            arguments.host_path,
        )
    )

    tasks = [(vol_instance, (cmd, _make_vol3_cfg(), False, lock)) for cmd in commands]
    successful, failed = [], []
    for command_name, is_success in pool.imap_unordered(vol3_wrapper, tasks):
        (successful if is_success else failed).append(command_name)

    # Make sure strings finishes before returning
    try:
        strings_future.get()
        console.print("[+] Strings complete !")
    except Exception as e:
        console.print(f"[!] Strings failed: {e}")
        
    return successful, failed


def run_analysis(arguments: argparse.Namespace) -> None:
    """Run the full analysis pipeline based on parsed CLI arguments."""
    for d in (
        "volatility3_symbols",
        "volatility2_profiles",
        "volatility3_cache",
        "volatility3_plugins",
    ):
        os.makedirs(os.path.join(os.getcwd(), d), exist_ok=True)

    if not arguments.light and not arguments.full:
        arguments.light = True

    output_dir = (
        getattr(arguments, "output_dir", None)
        or getattr(arguments, "output", None)
        or f"output_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)

    commands, vol_instance = _resolve_commands(arguments)

    max_procs = getattr(arguments, "processes", None)
    max_processes = min(max_procs, len(commands)) if max_procs else (os.cpu_count() or 4)
    start_time = time.time()

    console = Console(theme=Theme({"info": "dim cyan", "warning": "magenta", "danger": "bold red"}))
    _ensure_docker_image(arguments.image, console)
    console.print("\n[bold green][+] Launching all commands...[/bold green]\n")

    manager = multiprocessing.Manager()
    lock = manager.Lock()

    with multiprocessing.Pool(processes=max_processes) as pool:
        if arguments.mode == "vol2":
            successful_modules, failed_modules = _run_vol2_pool(
                pool, vol_instance, commands, arguments, output_dir, lock
            )
        else:
            successful_modules, failed_modules = _run_vol3_pool(
                pool, vol_instance, commands, arguments, output_dir, lock, console
            )

    _print_scan_summary(console, successful_modules, failed_modules, arguments)
    console.print(
        f"\n[bold yellow]⏱️  Time : {time.time() - start_time:.2f} seconds for {len(commands)} modules.[/bold yellow]"
    )


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate parsed CLI arguments, printing help and raising SystemExit on invalid input."""
    if args.mode is None:
        parser.print_help()
        raise SystemExit(1)

    if not args.linux and not args.windows:
        print("[-] --linux or --windows required.")
        raise SystemExit(1)

    if getattr(args, "fetch_symbol", False) and not args.linux:
        print("[-] --fetch-symbol only available with --linux")
        raise SystemExit(1)

    if args.mode == "vol2" and getattr(args, "fetch_symbol", False):
        print("[-] --fetch-symbol only available with vol3")
        raise SystemExit(1)

    if args.format not in ("json", "text"):
        print("Format not supported !")
        raise SystemExit(1)


def main():
    """Parse CLI arguments and dispatch to API server or analysis runner."""
    # Argument parsing for CLI usage
    parser = argparse.ArgumentParser("multivol")
    parser.add_argument("--api", action="store_true", help="Start API server")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode (hot reload)")
    parser.add_argument(
        "--host-path",
        type=str,
        required=False,
        default=None,
        help="Root path of the project on the Host machine (required for Docker-in-Docker)",
    )
    subparser = parser.add_subparsers(dest="mode", required=False)

    # Volatility2 argument group
    vol2_parser = subparser.add_parser("vol2", help="Use volatility2.")
    vol2_parser.add_argument(
        "--profiles-path",
        help="Path to the directory with the profiles.",
        default=os.path.join(os.getcwd(), "volatility2_profiles"),
    )
    vol2_parser.add_argument("--profile", help="Profile to use.", required=True)
    vol2_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol2_parser.add_argument(
        "--image",
        help="Docker image to use.",
        required=False,
        default="sp00kyskelet0n/volatility2",
    )
    vol2_parser.add_argument(
        "--commands",
        help="Commands to run : command1,command2,command3",
        required=False,
    )
    vol2_os_group = vol2_parser.add_mutually_exclusive_group(required=True)
    vol2_os_group.add_argument("--linux", action="store_true", help="For a Linux memory dump")
    vol2_os_group.add_argument("--windows", action="store_true", help="For a Windows memory dump")
    vol2_parser.add_argument("--light", action="store_true", help="Use the main modules.")
    vol2_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol2_parser.add_argument(
        "--format",
        help="Format of the outputs: json, text",
        required=False,
        default="text",
    )
    vol2_parser.add_argument(
        "--processes",
        type=int,
        required=False,
        default=None,
        help="Max number of concurrent processes.",
    )
    vol2_parser.add_argument(
        "--output",
        required=False,
        help="Directory where outputs will be written (Default: output_YYYY_MM_DD_HH_MM_SS).",
    )

    # Volatility3 argument group
    vol3_parser = subparser.add_parser("vol3", help="Use volatility3.")
    vol3_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol3_parser.add_argument(
        "--image",
        help="Docker image to use.",
        required=False,
        default="sp00kyskelet0n/volatility3",
    )
    vol3_parser.add_argument(
        "--symbols-path",
        help="Path to the directory with the symbols.",
        required=False,
        default=os.path.join(os.getcwd(), "volatility3_symbols"),
    )
    vol3_parser.add_argument(
        "--cache-path",
        help="Path to directory with the cache for volatility3.",
        required=False,
        default=os.path.join(os.getcwd(), "volatility3_cache"),
    )
    vol3_parser.add_argument(
        "--plugins-dir",
        help="Path to directory with the plugins",
        required=False,
        default=os.path.join(os.getcwd(), "volatility3_plugins"),
    )
    vol3_parser.add_argument(
        "--commands",
        help="Commands to run : command1,command2,command3",
        required=False,
    )
    vol3_os_group = vol3_parser.add_mutually_exclusive_group(required=True)
    vol3_os_group.add_argument("--linux", action="store_true", help="It's a Linux memory dump.")
    vol3_os_group.add_argument("--windows", action="store_true", help="It's a Windows memory dump.")
    vol3_parser.add_argument("--light", action="store_true", help="Use the principal modules.")
    vol3_parser.add_argument(
        "--fetch-symbol",
        action="store_true",
        help="Fetch automatically symbol from github.com/Abyss-W4tcher/volatility3-symbols",
        required=False,
    )
    vol3_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol3_parser.add_argument(
        "--format",
        help="Format of the outputs: json, text",
        required=False,
        default="text",
    )
    vol3_parser.add_argument(
        "--processes",
        type=int,
        required=False,
        default=None,
        help="Max number of concurrent processes",
    )
    vol3_parser.add_argument(
        "--output",
        required=False,
        help="Directory where outputs will be written (Default: output_YYYY_MM_DD_HH_MM_SS).",
    )

    # Global arguments
    parser.add_argument("--debug", action="store_true", help="Show executed Docker commands")
    parser.add_argument("--scan-id", help="Scan UUID for API status updates", required=False)

    args = parser.parse_args()

    if args.api:
        try:
            from .api_server import run_api  # pylint: disable=import-outside-toplevel
        except ImportError:
            from api_server import run_api  # pylint: disable=import-outside-toplevel
        run_api(run_analysis, debug_mode=args.dev)
        return

    _validate_args(parser, args)

    run_analysis(args)


if __name__ == "__main__":
    main()
