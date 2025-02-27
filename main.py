import subprocess, multiprocessing, time, os, argparse, sys
from multi_volatility2 import multi_volatility2
from multi_volatility3 import multi_volatility3

def runner(arguments):

    if arguments.mode == "vol2":
        if not args.light and not args.full:
            arguments.light = True

        volatility2_instance = multi_volatility2()
        output_dir = f"volatility2_{arguments.dump.split("/")[-1]}__output"
        os.makedirs(output_dir, exist_ok=True)
        if arguments.windows:
            if arguments.light:
                commands = volatility2_instance.getCommands("windows.light")
            else:
                commands = volatility2_instance.getCommands("windows.full")
        elif arguments.linux:
            if arguments.light:
                commands = volatility2_instance.getCommands("linux.light")
            else:
                commands = volatility2_instance.getCommands("linux.full")

    elif arguments.mode == "vol3":
        volatility3_instance = multi_volatility3()
        output_dir = f"volatility3_{arguments.dump.split("/")[-1]}__output"
        os.makedirs(output_dir, exist_ok=True)
        if arguments.windows:
            commands = volatility3_instance.getCommands("windows")
        elif arguments.linux:
            commands = volatility3_instance.getCommands("linux")

    max_processes = min(5, len(commands))

    start_time = time.time()

    print("\n[+] Launching all commands...\n")

    with multiprocessing.Pool(processes=max_processes) as pool:
        if arguments.mode == "vol2":
            pool.starmap(
                volatility2_instance.execute_command_volatility2, 
                [(cmd, 
                arguments.dump, 
                os.path.dirname(os.path.abspath(arguments.dump.split("/")[-1])), 
                arguments.profiles_path, 
                arguments.image, 
                arguments.profile, 
                output_dir
                ) for cmd in commands]
            )
        else:
            if arguments.symbols_path == "./volatility3_symbols":
           
                volatility3_instance.execute_command_volatility3("windows.info.Info", 
                                                                arguments.dump, 
                                                                os.path.dirname(os.path.abspath(arguments.dump.split("/")[-1])), 
                                                                arguments.symbols_path, 
                                                                arguments.image,
                                                                os.path.abspath(arguments.cache_path),
                                                                os.path.abspath(arguments.plugins_dir),
                                                                output_dir
                                                            )
        
            pool.starmap(
                volatility3_instance.execute_command_volatility3, 
                [(cmd, 
                arguments.dump, 
                os.path.dirname(os.path.abspath(arguments.dump.split("/")[-1])), 
                arguments.symbols_path, 
                arguments.image, 
                os.path.abspath(arguments.cache_path),
                os.path.abspath(arguments.plugins_dir), 
                output_dir
                ) for cmd in commands]
            )

    last_time = time.time()
    print(f"\n⏱️  Time : {last_time - start_time:.2f} seconds for {len(commands)} modules.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser("MultiVolatility")

    subparser = parser.add_subparsers(dest="mode", required=True)
    vol2_parser = subparser.add_parser("vol2", help="Use volatility2.")
    vol2_parser.add_argument("--profiles-path", help="Path to the directory with the profiles.", default="./volatility2_profiles")
    vol2_parser.add_argument("--profile", help="Profile to use.", required=True)
    vol2_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol2_parser.add_argument("--image", help="Docker image to use.", required=True)
    vol2_parser.add_argument("--linux", action="store_true", help="It's a Linux memory dump")
    vol2_parser.add_argument("--windows", action="store_true", help="It's a Windows memory dump")
    vol2_parser.add_argument("--light", action="store_true", help="Use the principal modules.")
    vol2_parser.add_argument("--full", action="store_true", help="Use 69 modules.")

    vol3_parser = subparser.add_parser("vol3", help="Use volatility3.")
    vol3_parser.add_argument("--dump", help="Dump to parse.", required=True)
    vol3_parser.add_argument("--image", help="Docker image to use.", required=True)
    vol3_parser.add_argument("--symbols-path", help="Path to the directory with the symbols.", required=False, default="./volatility3_symbols")
    vol3_parser.add_argument("--cache-path", help="Path to directory with the cache for volatility3 (in order to prevent all containers to download the symbols).", required=False, default="./volatility3_cache")
    vol3_parser.add_argument("--plugins-dir", help="Path to directory with the plugins", required=False, default="./volatility3_plugins")
    vol3_parser.add_argument("--linux", action="store_true", help="It's a Linux memory dump")
    vol3_parser.add_argument("--windows", action="store_true", help="It's a Windows memory dump")

    args = parser.parse_args()

    if not args.linux and not args.windows:
        print("[-] --linux or --windows required.")
        sys.exit(1)
    
    runner(args)
