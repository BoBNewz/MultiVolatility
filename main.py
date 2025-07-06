# main.py
# Entry point for MultiVolatility: orchestrates running Volatility2 and Volatility3 memory analysis in parallel using multiprocessing.
import multiprocessing, time, os, argparse, sys
from multi_volatility2 import multi_volatility2
from multi_volatility3 import multi_volatility3

def runner(arguments):
    # Ensure required directories exist for output, symbols, profiles, and plugins
    os.makedirs(os.path.join(os.getcwd(), "volatility3_symbols"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility2_profiles"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility3_cache"), exist_ok=True)
    os.makedirs(os.path.join(os.getcwd(), "volatility3_plugins"), exist_ok=True)

    # Default to light mode if neither light nor full is specified
    if not args.light and not args.full:
        arguments.light = True

    # Handle Volatility2 mode
    if arguments.mode == "vol2":
        volatility2_instance = multi_volatility2()
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
    max_processes = min(5, len(commands))
    start_time = time.time()
    print("\n[+] Launching all commands...\n")

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
                output_dir,
                arguments.dump_name,
                arguments.online,
                arguments.format
                ) for cmd in commands]
            )
        else:
            # Always run Info module first for Volatility3 if using default symbols path
            if arguments.symbols_path == os.path.join(os.getcwd(), "volatility3_symbols"):
                volatility3_instance.execute_command_volatility3("windows.info.Info", 
                                                                os.path.basename(arguments.dump), 
                                                                os.path.abspath(arguments.dump), 
                                                                arguments.symbols_path, 
                                                                arguments.image,
                                                                os.path.abspath(arguments.cache_path),
                                                                os.path.abspath(arguments.plugins_dir),
                                                                output_dir,
                                                                arguments.dump_name,
                                                                arguments.online,
                                                                arguments.format
                                                            )
            pool.starmap(
                volatility3_instance.execute_command_volatility3, 
                [(cmd, 
                os.path.basename(arguments.dump), 
                os.path.abspath(arguments.dump), 
                arguments.symbols_path, 
                arguments.image, 
                os.path.abspath(arguments.cache_path),
                os.path.abspath(arguments.plugins_dir), 
                output_dir,
                arguments.dump_name,
                arguments.online,
                arguments.format
                ) for cmd in commands]
            )

    last_time = time.time()
    print(f"\n⏱️  Time : {last_time - start_time:.2f} seconds for {len(commands)} modules.")

if __name__ == "__main__":
    # Argument parsing for CLI usage
    parser = argparse.ArgumentParser("MultiVolatility")
    subparser = parser.add_subparsers(dest="mode", required=True)

    # Volatility2 argument group
    vol2_parser = subparser.add_parser("vol2", help="Use volatility2.")
    vol2_parser.add_argument("--profiles-path", help="Path to the directory with the profiles.", default=os.path.join(os.getcwd(), "volatility2_profiles"))
    vol2_parser.add_argument("--profile", help="Profile to use.", required=True)
    vol2_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol2_parser.add_argument("--image", help="Docker image to use.", required=True)
    vol2_parser.add_argument("--commands", help="Commands to run : command1,command2,command3", required=False)
    vol2_parser.add_argument("--linux", action="store_true", help="It's a Linux memory dump")
    vol2_parser.add_argument("--windows", action="store_true", help="It's a Windows memory dump")
    vol2_parser.add_argument("--light", action="store_true", help="Use the principal modules.")
    vol2_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol2_parser.add_argument("--format", help="Format of the outputs: json, text", required=False, default="text")
    vol2_parser.add_argument("--online", action="store_true", help="Send data to backend for processing")
    vol2_parser.add_argument("--dump-name", type=str, required=False, help="Dump name for multivol backend.", default="default")

    # Volatility3 argument group
    vol3_parser = subparser.add_parser("vol3", help="Use volatility3.")
    vol3_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol3_parser.add_argument("--image", help="Docker image to use.", required=True)
    vol3_parser.add_argument("--symbols-path", help="Path to the directory with the symbols.", required=False, default=os.path.join(os.getcwd(), "volatility3_symbols"))
    vol3_parser.add_argument("--cache-path", help="Path to directory with the cache for volatility3.", required=False, default=os.path.join(os.getcwd(), "volatility3_cache"))
    vol3_parser.add_argument("--plugins-dir", help="Path to directory with the plugins", required=False, default=os.path.join(os.getcwd(), "volatility3_plugins"))
    vol3_parser.add_argument("--commands", help="Commands to run : command1,command2,command3", required=False)
    vol3_parser.add_argument("--linux", action="store_true", help="It's a Linux memory dump")
    vol3_parser.add_argument("--windows", action="store_true", help="It's a Windows memory dump")
    vol3_parser.add_argument("--light", action="store_true", help="Use the principal modules.")
    vol3_parser.add_argument("--full", action="store_true", help="Use all modules.")
    vol3_parser.add_argument("--format", help="Format of the outputs: json, text", required=False, default="text")
    vol3_parser.add_argument("--online", action="store_true", help="Send data to backend for processing")
    vol3_parser.add_argument("--dump-name", type=str, required=False, help="Dump name for multivol backend.", default="default")
    args = parser.parse_args()

    # Validate required OS type
    if not args.linux and not args.windows:
        print("[-] --linux or --windows required.")
        sys.exit(1)

    # Prevent unsupported combinations for Volatility3 Linux
    if (args.mode == "vol3" and args.linux and args.light) or (args.mode == "vol3" and args.linux and args.full):
        print("[-] --linux not available with --full or --light")
        sys.exit(1)

    # Force JSON output if sending online
    if args.online and (args.format == "text"):
        print("Modifying format outputs to JSON.")
        args.format = "json"

    # Validate output format
    if (args.format != "json") and (args.format != "text"):
        print("Format not supported !")
        sys.exit(1)
    
    # Start the runner with parsed arguments
    runner(args)
