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
                os.path.basename(arguments.dump), 
                os.path.abspath(arguments.dump), 
                arguments.profiles_path, 
                arguments.image, 
                arguments.profile, 
                output_dir
                ) for cmd in commands]
            )
        else:
            if arguments.symbols_path == "./volatility3_symbols":
           
                volatility3_instance.execute_command_volatility3("windows.info.Info", 
                                                                os.path.basename(arguments.dump), 
                                                                os.path.abspath(arguments.dump), 
                                                                arguments.symbols_path, 
                                                                arguments.image,
                                                                os.path.abspath(arguments.cache_path),
                                                                os.path.abspath(arguments.plugins_dir),
                                                                output_dir
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
                output_dir
                ) for cmd in commands]
            )

    last_time = time.time()
    print(f"\n⏱️  Time : {last_time - start_time:.2f} seconds for {len(commands)} modules.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser("MultiVolatility")

    subparser = parser.add_subparsers(dest="mode", required=True)
    vol2_parser = subparser.add_parser("vol2", help="Use volatility2.")
    vol2_parser.add_argument("-pp", "--profiles-path", help="Path to the directory with the profiles.", default="./volatility2_profiles")
    vol2_parser.add_argument("-p", "--profile", help="Profile to use.", required=True)
    vol2_parser.add_argument("-d", "--dump", help="Dump to parse.", required=True)
    vol2_parser.add_argument("-i", "--image", help="Docker image to use.", required=True)
    vol2_parser.add_argument("-l", "--linux", action="store_true", help="It's a Linux memory dump")
    vol2_parser.add_argument("-w", "--windows", action="store_true", help="It's a Windows memory dump")
    vol2_parser.add_argument("-li", "--light", action="store_true", help="Use the principal modules.")
    vol2_parser.add_argument("-f", "--full", action="store_true", help="Use 69 modules.")

    vol3_parser = subparser.add_parser("vol3", help="Use volatility3.")
    vol3_parser.add_argument("-d", "--dump", help="Dump to parse.", required=True)
    vol3_parser.add_argument("-i", "--image", help="Docker image to use.", required=True)
    vol3_parser.add_argument("-s", "--symbols-path", help="Path to the directory with the symbols.", required=False, default="./volatility3_symbols")
    vol3_parser.add_argument("-c", "--cache-path", help="Path to directory with the cache for volatility3.", required=False, default="./volatility3_cache")
    vol3_parser.add_argument("-p", "--plugins-dir", help="Path to directory with the plugins", required=False, default="./volatility3_plugins")
    vol3_parser.add_argument("-l", "--linux", action="store_true", help="It's a Linux memory dump")
    vol3_parser.add_argument("-w", "--windows", action="store_true", help="It's a Windows memory dump")

    args = parser.parse_args()

    if not args.linux and not args.windows:
        print("[-] --linux or --windows required.")
        sys.exit(1)
    
    runner(args)
