import docker
import time
import os
from rich import print as rprint

def resolve_path(path, host_path):
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

def safe_print(message, lock):
    if lock:
        with lock:
            rprint(message)
    else:
        rprint(message)

def get_strings(dump, dump_dir, output_dir, docker_image, lock=False, host_path=None):
    output_file = os.path.join(output_dir, f"strings_output.txt")
    host_output_dir = resolve_path(os.path.abspath(output_dir), host_path)
        
    host_dump_path = resolve_path(os.path.abspath(dump_dir), host_path)
    host_dump_dir = os.path.dirname(host_dump_path)

    volumes = {
        host_dump_dir: {'bind': '/dump_dir', 'mode': 'ro'},
        host_output_dir: {'bind': '/output', 'mode': 'rw'}
    }

    dump_filename = os.path.basename(dump)
    cmd_args = f"strings /dump_dir/{dump_filename}"
    
    client = docker.from_env()
    
    try:
        container = client.containers.run(
            image=docker_image,
            command=cmd_args,
            volumes=volumes,
            tty=True, 
            detach=True,
            remove=False
        )
            
        with open(output_file, "wb") as file:
            for chunk in container.logs(stream=True):
                file.write(chunk)
            
        container.wait()
        container.remove()

    except Exception as e:
        safe_print(f"[!] Error running strings: {e}", lock)