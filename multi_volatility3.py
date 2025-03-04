import subprocess
import multiprocessing
import time
import os
import argparse
import json

class multi_volatility3:
    def __init__(self):
        pass

    def generate_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir):
        return [
            "sudo", "docker", "run", "--rm", 
            "-v", f"{dump_dir}:/dumps/{dump}", 
            "-v", f"{cache_dir}:/home/root/.cache",
            "-v", f"{symbols_path}:/tmp", 
            "-v", f"{plugin_dir}:/root/plugins_dir",
            "-ti", docker_image,
            "vol",
            "-q",
            "-f", f"/dumps/{dump}",
            "-s", "/tmp",
            "-p", "/root/plugins_dir",
            "-r", "json",
            command
        ]

    def execute_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir, output_dir):
        print(f"[+] Starting {command}...")

        self.cmd = self.generate_command_volatility3(command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir)

        self.output_file = os.path.join(output_dir, f"{command}_output.json")
        with open(self.output_file, "w") as file:
            subprocess.run(self.cmd, stdout=file, stderr=file)
        
        time.sleep(0.5)

        with open(self.output_file,"r") as f:
            lines = f.readlines()

        with open(self.output_file,"w") as f:
            f.writelines(lines[2:])

        if command == "windows.filescan.FileScan":
            #If JSON format
            with open(os.path.join(output_dir, "windows.filescan.FileScan_filtered_output.json"), "w") as file:
                with open(self.output_file, "r") as full_filescan:
                    data = json.load(full_filescan)
                user_json_file = []
                for i in data:
                    if "Users" in i['Name']:
                        user_json_file.append(i)
                json.dump(user_json_file, file)

        print(f"[+] {command} finished.")
        return command

    def getCommands(self, opsys):
        if opsys == "windows":
            return ["windows.cmdline.CmdLine", 
                    "windows.cachedump.Cachedump", 
                    "windows.dlllist.DllList", 
                    "windows.driverirp.DriverIrp", 
                    "windows.drivermodule.DriverModule", 
                    "windows.driverscan.DriverScan", 
                    "windows.envars.Envars", 
                    "windows.filescan.FileScan", 
                    "windows.getservicesids.GetServiceSIDs", 
                    "windows.getsids.GetSIDs", 
                    "windows.handles.Handles", 
                    "windows.hashdump.Hashdump", 
                    "windows.lsadump.Lsadump", 
                    "windows.info.Info", 
                    "windows.malfind.Malfind", 
                    "windows.mftscan.MFTScan", 
                    "windows.modules.Modules", 
                    "windows.netscan.NetScan", 
                    "windows.netstat.NetStat", 
                    "windows.privileges.Privs", 
                    "windows.pslist.PsList", 
                    "windows.psscan.PsScan", 
                    "windows.pstree.PsTree", 
                    "windows.registry.hivelist.HiveList", 
                    "windows.registry.certificates.Certificates", 
                    "windows.registry.hivescan.HiveScan", 
                    "windows.registry.userassist.UserAssist", 
                    "windows.sessions.Sessions"
                ]
        elif opsys == "linux":
            return ["linux.bash.Bash", 
                    "linux.capabilities.Capabilities", 
                    "linux.check_syscall.Check_syscall", 
                    "linux.elfs.Elfs", 
                    "linux.envars.Envars", 
                    "linux.library_list.LibraryList", 
                    "linux.lsmod.Lsmod", 
                    "linux.lsof.Lsof", 
                    "linux.malfind.Malfind", 
                    "linux.mountinfo.MountInfo", 
                    "linux.psaux.PsAux", 
                    "linux.pslist.PsList", 
                    "linux.psscan.PsScan", 
                    "linux.pstree.PsTree", 
                    "linux.sockstat.Sockstat"
                ]