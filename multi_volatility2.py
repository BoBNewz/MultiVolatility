# multi_volatility2.py
# Implements Volatility2 memory analysis orchestration, Docker command generation, and backend communication.
import subprocess
import time
import os
import json
import yaml
import hashlib
import requests

class multi_volatility2:
    def __init__(self):
        # Constructor for multi_volatility2 class
        pass    
    
    def send_output_to_backend(self,lines,user_dump_name,command):
        # Sends the output of a command to the backend server as JSON
        try:
            command_output = ''.join(lines[-1])
            json_str_command_output = json.loads(command_output)
            self.send_json_to_backend(json_str_command_output,user_dump_name,command)
        except Exception as e:
            print(f"[!] An error occured while sending to backend : {e}")
    
    def read_config(self):
        # Reads backend configuration from config.yml
        with open("config.yml", "r") as f:
            data = yaml.safe_load(f)
        backend_address = data['config']['backend_address']
        backend_port = data['config']['backend_port']
        backend_password = data['config']['backend_password']
        return backend_address, backend_port, backend_password

    def sha512_hash(self, text: str) -> str:
        # Returns the SHA-512 hash of the given text
        return hashlib.sha512(text.encode("utf-8")).hexdigest()

    def send_json_to_backend(self, payload, dump_name, module_name):
        # Sends a JSON payload to the backend server with authentication
        backend_address, backend_port, backend_password = self.read_config()
        hashed_password = self.sha512_hash(backend_password)
        module_name = f"vol2_{module_name}"
        headers = {
            "Content-Type": "application/json",
            "dump-name": dump_name,
            "module-name": module_name,
            "api-password": hashed_password
        }
        response = requests.post(f"{backend_address}:{backend_port}/receive-json/", headers=headers, json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            print(f"[!] Request to backend failed: {e}")
            print("Response content:", response.text)
            return None
        print(f"[*] {module_name} output was sent to multivol backend")
        return response.json()

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

    def execute_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile, output_dir, user_dump_name,send_online, format):
        # Executes a Volatility2 command in Docker and handles output
        print(f"[+] Starting {command}...")
        if format == "json":
            self.cmd = self.generate_command_volatility2(command, dump, dump_dir, profiles_path, docker_image, profile, "json")
            self.output_file = os.path.join(output_dir, f"{command}_output.json")
        else:
            self.cmd = self.generate_command_volatility2(command, dump, dump_dir, profiles_path, docker_image, profile, "text")
            self.output_file = os.path.join(output_dir, f"{command}_output.txt")
        with open(self.output_file, "w") as file:
            subprocess.run(self.cmd, stdout=file, stderr=file)
        time.sleep(0.5)
        if format == "json":
            with open(self.output_file,"r") as f:
                lines = f.readlines()
            with open(self.output_file,"w") as f:
                f.writelines(lines[-1])
        # Optionally filter filescan output (commented out)
        """
        if command == "filescan":
            with open(os.path.join(output_dir, "filescan_filtered_output.json"), "w") as file:
                with open(self.output_file, "r") as full_filescan:
                    data = json.load(full_filescan)
                user_json_file = []
                for row in data["rows"]:
                    if "Users" in row[4]:
                        user_json_file.append(row)
                json.dump(user_json_file, file)
        """
        if send_online:
            self.send_output_to_backend(lines,user_dump_name,command)
        print(f"[+] {command} finished.")
        return command

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
