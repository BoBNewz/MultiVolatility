# multi_volatility3.py
# Implements Volatility3 memory analysis orchestration, Docker command generation, and backend communication.
import time
import os
import json
import re
import uuid
from rich import print as rprint
import yaml
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

    def execute_command_volatility3(self, command, dump, dump_dir, symbols_path, docker_image, cache_dir, plugin_dir, output_dir, format, quiet=False, lock=None, host_path=None, fetch_symbols=False, show_commands=False, custom_symbol=None, scan_id=None):
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
        
        # Debug logging for path resolution
        print(f"[DEBUG] dump={dump}, dump_dir={dump_dir}", flush=True)
        print(f"[DEBUG] host_dump_path={host_dump_path}, host_dump_dir={host_dump_dir}", flush=True)
        
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
        print(f"[DEBUG] dump_filename={dump_filename}, full path in container=/dump_dir/{dump_filename}", flush=True)
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
        
        # Debug: verify output path
        print(f"[DEBUG] output_dir={output_dir}, output_file={self.output_file}", flush=True)
        print(f"[DEBUG] output_dir exists: {os.path.exists(output_dir)}", flush=True)
        if show_commands:
            print(f"[DEBUG] Volatility 3 Command: {cmd_args}", flush=True)
            print(f"[DEBUG] Docker Volumes: {json.dumps(volumes, indent=2)}", flush=True)

        try:
            # Sanitize command name for Docker container name
            # Use scan_id for predictable naming so API can track container status
            sanitized_name = re.sub(r'[^a-zA-Z0-9_.-]', '', command)
            if scan_id:
                container_name = f"vol3_{scan_id[:8]}_{sanitized_name}"
            else:
                container_name = f"vol3_{sanitized_name}_{str(uuid.uuid4())[:8]}"

            container = client.containers.run(
                image=docker_image,
                name=container_name, # Name the container
                command=cmd_args,
                volumes=volumes,
                tty=True, 
                detach=True,
                remove=False
            )
            
            with open(self.output_file, "wb") as file:
                try:
                    for chunk in container.logs(stream=True):
                        file.write(chunk)
                except Exception as log_err:
                    # Handle Docker log rotation errors (common with long-running modules)
                    self.safe_print(f"[!] Log streaming interrupted: {log_err}, fetching remaining logs...", lock)
                    try:
                        # Fallback: fetch all logs at once instead of streaming
                        remaining_logs = container.logs(stream=False)
                        file.write(remaining_logs)
                    except:
                        pass  # Best effort - container may have finished
            
            wait_result = container.wait()
            exit_code = wait_result.get('StatusCode', 0)
            # Don't remove container - API will check status and clean up
            # container.remove()

        except Exception as e:
             self.safe_print(f"[!] Error running {command}: {e}", lock)
             return (command, False)
        
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
        
        # Check Exit Code first
        if exit_code != 0:
            success = False
        else:
            try:
                with open(self.output_file, "r") as f:
                    content = f.read()
                
                # Check for known error strings
                # "Volatility experienced": General runtime error
                # "vol.py: error:": Command line argument error
                # "usage: vol": Often printed on argument error
                if "Volatility experienced" in content or "vol.py: error:" in content or "vol: error:" in content:
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

        base_dir = os.path.dirname(os.path.abspath(__file__))

        yaml_path = os.path.join(base_dir, "plugins_list", f"vol3_{opsys}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"File not found : {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

            modules_list = data["modules"]

            return modules_list