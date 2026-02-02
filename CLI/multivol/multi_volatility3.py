# multi_volatility3.py
# Implements Volatility3 memory analysis orchestration, Docker command generation, and backend communication.
import time
import os
import json
import yaml
from rich import print as rprint
import docker

class multi_volatility3:
    def __init__(self):
        # Constructor for multi_volatility3 class
        pass

    def resolve_path(self, path, host_path):
        # If host_path is set, replacing the current working directory prefix with host_path
        if host_path: 
            if path.startswith("/storage"):
                 # Handle special storage mapping for Docker
                 # Map /storage -> {host_path}/storage/data
                 rel_path = os.path.relpath(path, "/storage")
                 return os.path.join(host_path, "storage", "data", rel_path)

            if path.startswith(os.getcwd()):
                rel_path = os.path.relpath(path, os.getcwd())
                return os.path.join(host_path, rel_path)
        return path

    def execute_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir, output_dir, format, quiet=False, lock=None, host_path=None, fetch_symbols=False, show_commands=False, custom_symbol=None):
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
             host_symbols_path: {'bind': '/symbols', 'mode': 'rw'},
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

        if custom_symbol:
            if show_commands:
                print(f"[DEBUG] Custom Symbol Selected: {custom_symbol}", flush=True)

        if fetch_symbols:
            base_args = f"{base_args} --remote-isf-url https://github.com/Abyss-W4tcher/volatility3-symbols/raw/master/banners/banners.json"

        if format == "json":
            self.output_file = os.path.join(output_dir, f"{command}_output.json")
            cmd_args = f"{base_args} -r json {command}"
        else:
            self.output_file = os.path.join(output_dir, f"{command}_output.txt")
            cmd_args = f"{base_args} {command}"
            
        if show_commands:
            print(f"[DEBUG] Volatility 3 Command: {cmd_args}", flush=True)
            print(f"[DEBUG] Docker Volumes: {json.dumps(volumes, indent=2)}", flush=True)

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

        with open(f"plugins_list/vol3_{opsys}.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

            modules_list = data["modules"]

            return modules_list