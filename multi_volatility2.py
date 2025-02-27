import subprocess
import multiprocessing
import time
import os
import argparse

class multi_volatility2:
    def __init__(self):
        pass
        
    def generate_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile):
        return [
            "docker", "run", "--rm", 
            "-v", f"{dump_dir}:/dumps", 
            "-v", f"{profiles_path}:/home/vol/profiles",  
            "-t", docker_image, "--plugins=/home/vol/profiles",
            "-f", f"/dumps/{dump}",
            f"--profile={profile}",
            f"--output=json",
            f"{command}"
        ]

    def execute_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile, output_dir):
        print(f"[+] Starting {command}...")

        self.cmd = self.generate_command_volatility2(command, dump, dump_dir, profiles_path, docker_image, profile)
        
        self.output_file = os.path.join(output_dir, f"{command}_output.json")
        with open(self.output_file, "w") as file:
            subprocess.run(self.cmd, stdout=file, stderr=file)
        
        time.sleep(0.5)

        with open(self.output_file,"r") as f:
            lines = f.readlines()

        with open(self.output_file,"w") as f:
            f.writelines(lines[-1])

        """
        if command == "filescan":
            with open(os.path.join(output_dir, "filescan_filtered_output.txt"), "w") as file:
                with open(self.output_file, "r") as full_filescan:
                    for line in full_filescan:
                        if "Users" in line:
                            file.write(line)
        """

        print(f"[+] {command} finished.")
        return command

    def getCommands(self, opsys):
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