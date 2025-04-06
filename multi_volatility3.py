import subprocess
import time
import os
import json
import requests
import hashlib
import yaml
class multi_volatility3:
    def __init__(self):
        pass

    def send_output_to_backend(self,lines,user_dump_name,command):
        try:
            command_output = ''.join(lines[2:])
            json_str_command_output = json.loads(command_output)
            self.send_json_to_backend(json_str_command_output,user_dump_name,command)
        except Exception as e:
            print(f"[!] An error occured while sending to backend : {e}")

    def read_config(self):
        with open("config.yml", "r") as f:
            data = yaml.safe_load(f)
        backend_address = data['config']['backend_address']
        backend_port = data['config']['backend_port']
        backend_password = data['config']['backend_password']
        return backend_address, backend_port, backend_password

    def sha512_hash(self, text: str) -> str:
        return hashlib.sha512(text.encode("utf-8")).hexdigest()

    def send_json_to_backend(self, payload, dump_name, module_name):
        backend_address, backend_port, backend_password = self.read_config()
        hashed_password = self.sha512_hash(backend_password)

        module_name = f"vol3_{module_name}"
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

    def generate_command_volatility3_json(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir):
        return [
            "docker", "run", "--rm", 
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
    
    def generate_command_volatility3_text(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir):
        return [
            "docker", "run", "--rm", 
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
            command
        ]

    def execute_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir, output_dir,user_dump_name,send_online, format):
        print(f"[+] Starting {command}...")

        if format == "json":
            self.cmd = self.generate_command_volatility3_json(command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir)
            self.output_file = os.path.join(output_dir, f"{command}_output.json")
        else:
            self.cmd = self.generate_command_volatility3_text(command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir)
            self.output_file = os.path.join(output_dir, f"{command}_output.txt")

        with open(self.output_file, "w") as file:
            subprocess.run(self.cmd, stdout=file, stderr=file)
        
        time.sleep(0.5)

        if format == "json":
            with open(self.output_file,"r") as f:
                lines = f.readlines()

            with open(self.output_file,"w") as f:
                f.writelines(lines[2:])

        """
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
        """
        
        if send_online:
            self.send_output_to_backend(lines,user_dump_name,command)
        print(f"[+] {command} finished.")
        return command

    def getCommands(self, opsys):
        if opsys == "windows.full":
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
        elif opsys == "windows.light":
            return ["windows.cmdline.CmdLine",
                    "windows.filescan.FileScan",
                    "windows.netscan.NetScan",
                    "windows.netstat.NetStat",
                    "windows.pslist.PsList",
                    "windows.psscan.PsScan",
                    "windows.pstree.PsTree",
                    "windows.dlllist.DllList",
                    "windows.hashdump.Hashdump"
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