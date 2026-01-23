# multi_volatility3.py
# Implements Volatility3 memory analysis orchestration, Docker command generation, and backend communication.
import time
import os
import json
from rich import print as rprint
import docker


class multi_volatility3:
    def __init__(self):
        # Constructor for multi_volatility3 class
        pass

    def resolve_path(self, path, host_path):
        # If host_path is set, replacing the current working directory prefix with host_path
        if host_path and path.startswith(os.getcwd()):
            rel_path = os.path.relpath(path, os.getcwd())
            return os.path.join(host_path, rel_path)
        return path


    def generate_command_volatility3_json(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir):
        # Generates the Docker command to run a Volatility3 module with JSON output
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
        # Generates the Docker command to run a Volatility3 module with text output
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

    def execute_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir, output_dir, format, quiet=False, lock=None, host_path=None):
        # Executes a Volatility3 command in Docker and handles output
        if not quiet:
            self.safe_print(f"[+] Starting {command}...", lock)
        
        client = docker.from_env()

        # Resolve paths for DooD
        host_symbols_path = self.resolve_path(os.path.abspath(symbols_path), host_path)
        host_cache_path = self.resolve_path(os.path.abspath(cache_dir), host_path)
        host_plugin_dir = self.resolve_path(os.path.abspath(plugin_dir), host_path)
        host_output_dir = self.resolve_path(os.path.abspath(output_dir), host_path)
        
        host_dump_path = self.resolve_path(os.path.abspath(dump_dir), host_path)
        host_dump_dir = os.path.dirname(host_dump_path)
        
        volumes = {
             host_dump_dir: {'bind': '/dump_dir', 'mode': 'ro'},
             host_symbols_path: {'bind': '/symbols', 'mode': 'ro'},
             host_cache_path: {'bind': '/root/.cache/volatility3', 'mode': 'rw'},
             host_plugin_dir: {'bind': '/plugins', 'mode': 'ro'},
             host_output_dir: {'bind': '/output', 'mode': 'rw'}
        }
        
        # Base arguments
        # Base arguments with new volume paths:
        # dump_dir -> /dump_dir
        # symbols -> /symbols
        # cache -> /root/.cache/volatility3
        # plugins -> /plugins
        
        # NOTE: -f expects the file path. Volume maps dump_dir to /dump_dir. 
        # So dump file is at /dump_dir/basename(dump)
        dump_filename = os.path.basename(dump)
        base_args = f"vol -q -f /dump_dir/{dump_filename} -s /symbols -p /plugins"

        if format == "json":
            self.output_file = os.path.join(output_dir, f"{command}_output.json")
            cmd_args = f"{base_args} -r json {command}"
        else:
            self.output_file = os.path.join(output_dir, f"{command}_output.txt")
            cmd_args = f"{base_args} {command}"

        try:
            container = client.containers.run(
                image=docker_image,
                command=cmd_args,
                volumes=volumes,
                tty=True, 
                detach=True,
                remove=False
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
                if lines:
                     with open(self.output_file,"w") as f:
                        f.writelines(lines[2:])
            except:
                pass
        
        # Filescan filtering logic (commented out in original)
        """
        if command == "windows.filescan.FileScan":
            try:
                with open(os.path.join(output_dir, "windows.filescan.FileScan_filtered_output.json"), "w") as file:
                   # ... implementation details omitted as logic matches original structure ...
                   pass
            except:
                pass
        """



        if not quiet:
            self.safe_print(f"[+] {command} finished.", lock)
            
        # Validation
        success = False
        try:
            with open(self.output_file, "r") as f:
                content = f.read()
            
            # Check for known error string regardless of format
            if "Volatility experienced" in content:
                success = False
            elif format == "json":
                # Simple validation check matching API logic
                start_index = content.find('[')
                if start_index == -1:
                    start_index = content.find('{')
                
                if start_index != -1:
                    json.loads(content[start_index:])
                    success = True
                else:
                    # Fallback check
                     lines = content.splitlines()
                     if len(lines) > 1:
                         json.loads('\n'.join(lines[1:]))
                         success = True
            else:
                success = True # Assume text output is successful if no crash and no error string
        except:
            success = False

        return (command, success)

    def safe_print(self, message, lock):
        if lock:
            with lock:
                rprint(message)
        else:
            rprint(message)

    def getCommands(self, opsys):
        # Returns a list of Volatility3 commands for the specified OS and mode
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
                    "linux.sockstat.Sockstat",
                    "linux.boottime.Boottime",
                    "linux.check_creds.Check_creds",
                    "linux.hidden_modules.Hidden_modules",
                    "linux.ip.Addr",
                    "linux.ip.Link",
                    "linux.keyboard_notifiers.Keyboard_notifiers",
                    "linux.modxview.Modxview",
                    "linux.netfilter.Netfilter",
                    "linux.pagecache.Files",
                    "linux.pidhashtable.PIDHashTable",
                    "linux.tracing.ftrace.CheckFtrace",
                    "linux.tracing.perf_events.PerfEvents",
                    "linux.tracing.tracepoints.CheckTracepoints",
                    "linux.tty_check.tty_check"
                ]
