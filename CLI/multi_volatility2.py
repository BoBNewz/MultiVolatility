# multi_volatility2.py
# Implements Volatility2 memory analysis orchestration, Docker command generation, and backend communication.
import time
import os
import json
from rich import print as rprint
import docker


class multi_volatility2:
    def __init__(self):
        # Constructor for multi_volatility2 class
        pass
    
    def resolve_path(self, path, host_path):
        # If host_path is set, replacing the current working directory prefix with host_path
        if host_path and path.startswith(os.getcwd()):
            rel_path = os.path.relpath(path, os.getcwd())
            return os.path.join(host_path, rel_path)
        return path
    
    def generate_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile, format):
        # Generates the Docker command to run a Volatility2 module
        return [
            "docker", "run", "--rm", 
            "-v", f"{dump_dir}:/dumps/{dump}", 
            "-v", f"{profiles_path}:/home/vol/profiles",  
            "-t", docker_image, "--plugins=/home/vol/profiles",
            "-f", f"/dumps/{dump}",
            f"--profile={profile}",
            f"--output={format}",
            f"{command}"
        ]

    def execute_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile, output_dir, format, quiet=False, lock=None, host_path=None):
        # Executes a Volatility2 command in Docker and handles output
        if not quiet:
            self.safe_print(f"[+] Starting {command}...", lock)
        
        client = docker.from_env()

        # Resolve paths for DooD
        host_profiles_path = self.resolve_path(os.path.abspath(profiles_path), host_path)
        host_dump_path_src = self.resolve_path(os.path.abspath(dump_dir), host_path) # dump_dir here is actually the full file path from main.py
        host_output_dir = self.resolve_path(os.path.abspath(output_dir), host_path)

        volumes = {
            host_dump_path_src: {'bind': f'/dumps/{dump}', 'mode': 'rw'},
            host_profiles_path: {'bind': '/home/vol/profiles', 'mode': 'rw'},
            host_output_dir: {'bind': '/output', 'mode': 'rw'}
        }
        
        # Construct the command string to run inside the container
        cmd_args = f"--plugins=/home/vol/profiles -f /dumps/{dump} --profile={profile} --output={format} {command}"

        if format == "json":
            self.output_file = os.path.join(output_dir, f"{command}_output.json")
        else:
            self.output_file = os.path.join(output_dir, f"{command}_output.txt")
            
        try:
            container = client.containers.run(
                image=docker_image,
                command=cmd_args,
                volumes=volumes,
                tty=True, # Corresponds to -t
                remove=False,
                detach=True
            )
            
            with open(self.output_file, "wb") as file:
                for chunk in container.logs(stream=True):
                    file.write(chunk)
            
            container.wait()
            container.remove()

        except Exception as e:
             self.safe_print(f"[!] Error running {command}: {e}", lock)

        time.sleep(0.5)
        if format == "json":
            try:
                with open(self.output_file,"r") as f:
                    lines = f.readlines()
                if lines: # Check if lines is not empty
                    with open(self.output_file,"w") as f:
                        f.writelines(lines[-1])
            except:
                 pass
        


        if not quiet:
            self.safe_print(f"[+] {command} finished.", lock)
        return command

    def safe_print(self, message, lock):
        if lock:
            with lock:
                rprint(message)
        else:
            rprint(message)

    def getCommands(self, opsys):
        # Returns a list of Volatility2 commands for the specified OS and mode
        if opsys == "windows.light":
            return ["cmdline",
                    "cmdscan",
                    "connscan",
                    "consoles",
                    "dlllist",
                    "filescan",
                    "hashdump",
                    "malfind",
                    "psscan",
                    "pslist",
                    "pstree",
                    "psxview",
                ]
        elif opsys == "windows.full":
            return ["cmdline",
                    "cmdscan",
                    "connscan",
                    "consoles",
                    "dlllist",
                    "filescan",
                    "hashdump",
                    "malfind",
                    "mftparser",
                    "psscan",
                    "pslist",
                    "pstree",
                    "psxview",
                    "amcache",
                    "atoms",
                    "autoruns",
                    "bitlocker",
                    "cachedump",
                    "chromecookies",
                    "chromedownloads",
                    "chromehistory",
                    "chromevisits",
                    "clipboard",
                    "connections",
                    "devicetree",
                    "directoryenumerator",
                    "driverirp",
                    "drivermodule",
                    "driverscan",
                    "envars",
                    "evtlogs",
                    "firefoxcookies",
                    "firefoxdownloads",
                    "firefoxhistory",
                    "gahti",
                    "getservicesids",
                    "getsids",
                    "handles",
                    "hivelist",
                    "hivescan",
                    "hpakinfo",
                    "lsadump",
                    "mbrparser",
                    "messagehooks",
                    "modscan",
                    "modules",
                    "multiscan",
                    "mutantscan",
                    "networkpackets",
                    "prefetchparser",
                    "privs",
                    "psinfo",
                    "schtasks",
                    "screenshot",
                    "servicediff",
                    "sessions",
                    "shellbags",
                    "shimcache",
                    "sockets",
                    "sockscan",
                    "ssdt",
                    "svcscan",
                    "symlinkscan",
                    "thrdscan",
                    "threads",
                    "unloadedmodules",
                    "userassist",
                    "userhandles",
                ]
        elif opsys == "linux.light":
            return ["linux_bash",
                    "linux_ifconfig",
                    "linux_malfind",
                    "linux_netscan",
                    "linux_enumerate_files",
                    "linux_netstat",
                    "linux_psaux",
                    "linux_pslist",
                    "linux_psscan",
                    "linux_pstree",
                    "linux_psxview"
                ]
        elif opsys == "linux.full":
            return ["linux_banner",
                    "linux_bash",
                    "linux_ifconfig",
                    "linux_malfind",
                    "linux_netscan",
                    "linux_netstat",
                    "linux_psaux",
                    "linux_pslist",
                    "linux_psscan",
                    "linux_pstree",
                    "linux_psxview",
                    "linux_apihooks",
                    "linux_arp",
                    "linux_aslr_shift",
                    "linux_bash_env",
                    "linux_bash_hash",
                    "linux_check_afinfo",
                    "linux_check_creds",
                    "linux_check_fop",
                    "linux_check_idt",
                    "linux_check_inline_kernel",
                    "linux_check_modules",
                    "linux_check_syscall",
                    "linux_check_syscall_arm",
                    "linux_check_tty",
                    "linux_cpuinfo",
                    "linux_dentry_cache",
                    "linux_dmesg",
                    "linux_dynamic_env",
                    "linux_elfs",
                    "linux_getcwd",
                    "linux_hidden_modules",
                    "linux_info_regs",
                    "linux_iomem",
                    "linux_kernel_opened_files",
                    "linux_keyboard_notifiers",
                    "linux_ldrmodules",
                    "linux_library_list",
                    "linux_list_raw",
                    "linux_lsmod",
                    "linux_lsof",
                    "linux_memmap",
                    "linux_mount",
                    "linux_mount_cache",
                    "linux_netfilter",
                    "linux_pidhashtable",
                    "linux_pkt_queues",
                    "linux_plthook",
                    "linux_proc_maps",
                    "linux_proc_maps_rb",
                    "linux_process_hollow",
                    "linux_psenv",
                    "linux_pslist_cache",
                    "linux_route_cache",
                    "linux_sk_buff_cache",
                    "linux_threads",
                    "linux_truecrypt_passphrase"
                ]
