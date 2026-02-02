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

    def execute_command_volatility2(self, command, dump, dump_dir, profiles_path, docker_image, profile, output_dir, format, quiet=False, lock=None, host_path=None, show_commands=False):
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
        if show_commands:
            print(f"[DEBUG] Volatility 2 Command: vol.py {cmd_args}", flush=True)

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

        base_dir = os.path.dirname(os.path.abspath(__file__))

        yaml_path = os.path.join(base_dir, "plugins_list", f"vol2_{opsys}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"File not found : {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

            modules_list = data["modules"]

            return modules_list
