# multivol.py
# Entry point for MultiVolatility: orchestrates running Volatility2 and Volatility3 memory analysis in parallel using multiprocessing.
import multiprocessing, time, os, argparse, sys
import docker
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

try:
    from .multi_volatility2 import multi_volatility2
    from .multi_volatility3 import multi_volatility3
except ImportError:
    from multi_volatility2 import multi_volatility2
    from multi_volatility3 import multi_volatility3

# Wrapper for Volatility 3 to use with imap
def vol3_wrapper(packed_args):
    instance, args = packed_args
    return instance.execute_command_volatility3(*args)

def runner(arguments):
    # Ensure required directories exist for output, symbols, profiles, and plugins
    os.makedirs(os.path.join(os.getcwd(), "volatility3_symbols"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility2_profiles"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility3_cache"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility3_plugins"), exist_ok=True)

    # Default to light mode if neither light nor full is specified
    if not arguments.light and not arguments.full:
        arguments.light = True

    # Handle Volatility2 mode
    if arguments.mode == "vol2":
        volatility2_instance = multi_volatility2()
        if hasattr(arguments, "output_dir") and arguments.output_dir:
            output_dir = arguments.output_dir
        else:
            output_dir = f"volatility2_{os.path.basename(arguments.dump)}__output"
        os.makedirs(output_dir, exist_ok=True)
        # Determine commands to run based on arguments
        if arguments.commands:
            commands = arguments.commands.split(",")
        elif arguments.windows:
            if arguments.light:
                commands = volatility2_instance.getCommands("windows.light")
            else:
                commands = volatility2_instance.getCommands("windows.full")
        elif arguments.linux:
            if arguments.light:
                commands = volatility2_instance.getCommands("linux.light")
            else:
                commands = volatility2_instance.getCommands("linux.full")

    # Handle Volatility3 mode
    elif arguments.mode == "vol3":
        volatility3_instance = multi_volatility3()
        if hasattr(arguments, "output_dir") and arguments.output_dir:
            output_dir = arguments.output_dir
        else:
            output_dir = f"volatility3_{os.path.basename(arguments.dump)}__output"
        os.makedirs(output_dir, exist_ok=True)
        # Determine commands to run based on arguments
        if arguments.commands:
            commands = arguments.commands.split(",")
        elif arguments.windows:
            if arguments.light:
                commands = volatility3_instance.getCommands("windows.light")
            else:
                commands = volatility3_instance.getCommands("windows.full")
        elif arguments.linux:
            commands = volatility3_instance.getCommands("linux")

    # Limit the number of parallel processes
    # Default to len(commands) (unlimited) if processes arg is not set or None
    max_procs = getattr(arguments, 'processes', None)
    if max_procs is None:
        # Default to CPU count to avoid system thrashing with too many Docker containers
        try:
            max_processes = os.cpu_count() or 4
        except:
            max_processes = 4
    else:
        max_processes = min(max_procs, len(commands))
    start_time = time.time()
    
    custom_theme = Theme({"info": "dim cyan", "warning": "magenta", "danger": "bold red"})
    console = Console(theme=custom_theme)

    # Docker Image Check & Pull
    try:
        client = docker.from_env()
        image_name = arguments.image
        # Check if --image was passed in args. rudimentary check.
        user_provided_image = "--image" in sys.argv
        
        try:
            client.images.get(image_name)
            if not user_provided_image:
                 console.print(f"[dim cyan][*] No --image provided, using default image: {image_name}[/dim cyan]")
        except docker.errors.ImageNotFound:
            msg = f"[*] No --image provided, pulling default image: {image_name}" if not user_provided_image else f"[*] Pulling image: {image_name}"
            
            # Use Progress with custom columns to put spinner at the end
            with Progress(
                TextColumn("{task.description}"),
                SpinnerColumn("dots"),
                transient=True,
                console=console
            ) as progress:
                progress.add_task(f"[bold green]{msg}[/bold green]", total=None)
                client.images.pull(image_name)
            
            # Re-print the message so it persists in the log
            console.print(f"[bold green]{msg}[/bold green]")
            console.print(f"[bold green][*] Image {image_name} ready.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Warning: Docker check failed: {e}[/bold red]")
        # We don't exit here, we let the individual/pool commands fail if they must, or maybe user has local setup issues.

    console.print("\n[bold green][+] Launching all commands...[/bold green]\n")

    # Use multiprocessing Manager for Lock
    manager = multiprocessing.Manager()
    lock = manager.Lock()
    
    # Use multiprocessing to run commands in parallel
    with multiprocessing.Pool(processes=max_processes) as pool:
        if arguments.mode == "vol2":
            pool.starmap(
                volatility2_instance.execute_command_volatility2, 
                [(cmd, 
                os.path.basename(arguments.dump), 
                os.path.abspath(arguments.dump), 
                arguments.profiles_path, 
                arguments.image, 
                arguments.profile, 
                output_dir, # output_dir
                arguments.format,
                False, # quiet
                lock,  # lock
                arguments.host_path,
                getattr(arguments, "debug", False)
                ) for cmd in commands]
            )
        else:
            # Enforce priority execution for Info module to ensure symbols are downloaded/cached
            if arguments.windows:
                info_module = "windows.info.Info"
            else:
                info_module = "linux.bash.Bash"
            if arguments.windows or arguments.linux:
                if info_module in commands:
                    commands.remove(info_module)
                    volatility3_instance.execute_command_volatility3(info_module, 
                                                                    os.path.basename(arguments.dump), 
                                                                    os.path.abspath(arguments.dump), 
                                                                    arguments.symbols_path, 
                                                                    arguments.image,
                                                                    os.path.abspath(arguments.cache_path),
                                                                    os.path.abspath(arguments.plugins_dir),
                                                                    output_dir,
                                                                    arguments.format,
                                                                    False, # quiet
                                                                    lock,  # lock
                                                                    arguments.host_path,
                                                                    True if getattr(arguments, "fetch_symbol", False) else False,
                                                                    getattr(arguments, "debug", False),
                                                                    getattr(arguments, "custom_symbol", None)
                                                                )

            
            # Prepare arguments for imap
            # We must pass the instance because wrapper is global and doesn't see local variable
            tasks_args = [(volatility3_instance, (cmd, 
                os.path.basename(arguments.dump), 
                os.path.abspath(arguments.dump), 
                arguments.symbols_path, 
                arguments.image, 
                os.path.abspath(arguments.cache_path),
                os.path.abspath(arguments.plugins_dir), 
                output_dir,
                arguments.format,
                False, # quiet=False so we see the output as it happens
                lock, # lock
                arguments.host_path,
                True if getattr(arguments, "fetch_symbol", False) else False,
                getattr(arguments, "debug", False),
                getattr(arguments, "custom_symbol", None)
                )) for cmd in commands]
            
            # Progress counters
            success_count = 0
            failed_count = 0
            successful_modules = []
            failed_modules = []
            
            # Use imap_unordered for real-time results collection
            for result in pool.imap_unordered(vol3_wrapper, tasks_args):
                command_name, is_success = result
                
                if is_success:
                    success_count += 1
                    successful_modules.append(command_name)
                else:
                    failed_count += 1
                    failed_modules.append(command_name)
                    if arguments.format == "json":
                         console.print(f"[red][!] Failed to validate JSON for {command_name}[/red]")
            
            console.print(f"\n[bold green]Scan Complete![/bold green] Success: {success_count}, Failed: {failed_count}")
            
            if successful_modules:
                console.print("\n[bold green]Successful Modules:[/bold green]")
                for mod in successful_modules:
                    console.print(f"  - [green]{mod}[/green]")
            
            if failed_modules:
                console.print("\n[bold red]Failed Modules:[/bold red]")
                for mod in failed_modules:
                    console.print(f"  - [red]{mod}[/red]")

    last_time = time.time()
    console.print(f"\n[bold yellow]⏱️  Time : {last_time - start_time:.2f} seconds for {len(commands)} modules.[/bold yellow]")


def main():
    # Argument parsing for CLI usage
    parser = argparse.ArgumentParser("MultiVolatility")
    parser.add_argument("--api", action="store_true", help="Start API server")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode (hot reload)")
    parser.add_argument("--host-path", type=str, required=False, default=None, help="Root path of the project on the Host machine (required for Docker-in-Docker)")
    subparser = parser.add_subparsers(dest="mode", required=False)

    # Volatility2 argument group
    vol2_parser = subparser.add_parser("vol2", help="Use volatility2.")
    vol2_parser.add_argument("--profiles-path", help="Path to the directory with the profiles.", default=os.path.join(os.getcwd(), "volatility2_profiles"))
    vol2_parser.add_argument("--profile", help="Profile to use.", required=True)
    vol2_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol2_parser.add_argument("--image", help="Docker image to use.", required=False, default="sp00kyskelet0n/volatility2")
    vol2_parser.add_argument("--commands", help="Commands to run : command1,command2,command3", required=False)
    vol2_os_group = vol2_parser.add_mutually_exclusive_group(required=True)
    vol2_os_group.add_argument("--linux", action="store_true", help="For a Linux memory dump")
    vol2_os_group.add_argument("--windows", action="store_true", help="For a Windows memory dump")
    vol2_parser.add_argument("--light", action="store_true", help="Use the main modules.")
    vol2_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol2_parser.add_argument("--format", help="Format of the outputs: json, text", required=False, default="text")
    vol2_parser.add_argument("--processes", type=int, required=False, default=None, help="Max number of concurrent processes")

    # Volatility3 argument group
    vol3_parser = subparser.add_parser("vol3", help="Use volatility3.")
    vol3_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol3_parser.add_argument("--image", help="Docker image to use.", required=False, default="sp00kyskelet0n/volatility3")
    vol3_parser.add_argument("--symbols-path", help="Path to the directory with the symbols.", required=False, default=os.path.join(os.getcwd(), "volatility3_symbols"))
    vol3_parser.add_argument("--cache-path", help="Path to directory with the cache for volatility3.", required=False, default=os.path.join(os.getcwd(), "volatility3_cache"))
    vol3_parser.add_argument("--plugins-dir", help="Path to directory with the plugins", required=False, default=os.path.join(os.getcwd(), "volatility3_plugins"))
    vol3_parser.add_argument("--commands", help="Commands to run : command1,command2,command3", required=False)
    vol3_os_group = vol3_parser.add_mutually_exclusive_group(required=True)
    vol3_os_group.add_argument("--linux", action="store_true", help="It's a Linux memory dump")
    vol3_os_group.add_argument("--windows", action="store_true", help="It's a Windows memory dump")
    vol3_parser.add_argument("--light", action="store_true", help="Use the principal modules.")
    vol3_parser.add_argument("--fetch-symbol", action="store_true", help="Fetch automatically symbol from github.com/Abyss-W4tcher/volatility3-symbols", required=False)
    vol3_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol3_parser.add_argument("--format", help="Format of the outputs: json, text", required=False, default="text")
    vol3_parser.add_argument("--processes", type=int, required=False, default=None, help="Max number of concurrent processes")
    
    # Global arguments
    parser.add_argument("--debug", action="store_true", help="Show executed Docker commands")

    args = parser.parse_args()

    if args.api:
        try:
            from .api import run_api
        except ImportError:
            from api import run_api
        run_api(runner, debug_mode=args.dev)
        sys.exit(0)

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    # Validate required OS type
    if not args.linux and not args.windows:
        print("[-] --linux or --windows required.")
        sys.exit(1)

    # Prevent unsupported combinations for Volatility3 Linux
    if (args.mode == "vol3" and args.linux and args.light) or (args.mode == "vol3" and args.linux and args.full):
        print("[-] --linux not available with --full or --light")
        sys.exit(1)

    if getattr(args, "fetch_symbol", False) and not args.linux:
        print("[-] --fetch-symbol only available with --linux")
        sys.exit(1)

    # Validate output format
    if (args.format != "json") and (args.format != "text"):
        print("Format not supported !")
        sys.exit(1)
    
    # Start the runner with parsed arguments
    runner(args)

if __name__ == "__main__":
    main()
