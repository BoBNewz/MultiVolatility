import os
import hashlib
import time
import json
import sqlite3
from .database import get_db_connection

def resolve_host_path(container_path):
    """
    Translates a path inside the container (e.g., /app/storage/...) 
    to the equivalent path on the host, based on HOST_PATH env var.
    """
    host_base = os.environ.get("HOST_PATH")
    if not host_base:
         print("[WARNING] HOST_PATH not set. Docker volumes might map incorrectly if not using named volumes.")
         return container_path # Fallback, might work if paths somehow align or not using docker-in-docker
         
    try:
        from .config import BASE_DIR
        
        # If the container_path is inside BASE_DIR, we translate it
        if container_path.startswith(BASE_DIR):
             # e.g., /app/outputs/volatility3_1234 -> outputs/volatility3_1234
             rel_path = os.path.relpath(container_path, BASE_DIR)
             return os.path.join(host_base, rel_path)
             
        # Fallback to the old storage hack just in case
        if 'storage' in container_path:
             rel_path = container_path[container_path.find('storage'):]
             return os.path.join(host_base, rel_path)
    except:
        pass
    return container_path # Fallback

def calculate_sha256(filepath):
    """Calculates SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_file_hash(filepath):
    """Gets cached hash or calculates it."""
    hash_file = filepath + ".sha256"
    if os.path.exists(hash_file):
        try:
            with open(hash_file, 'r') as f:
                return f.read().strip()
        except:
            pass
    
    # Calculate and cache
    try:
        file_hash = calculate_sha256(filepath)
        with open(hash_file, 'w') as f:
            f.write(file_hash)
        return file_hash
    except Exception as e:
        print(f"[ERROR] Failed to calc hash for {filepath}: {e}")
        return "Error"

def clean_and_parse_json(filepath):
    """Helper to parse JSON from Volatility output files, handling errors gracefully."""
    if not os.path.exists(filepath):
        print(f"[WARN] File not found: {filepath}")
        return {"error": "File not found", "raw_output": ""}

    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        start_index = content.find('[')
        if start_index == -1:
            start_index = content.find('{')
        
        parsed_data = None
        if start_index != -1:
            try:
                json_content = content[start_index:]
                parsed_data = json.loads(json_content)
            except:
                pass # Try fallback
        
        if parsed_data is None:
             lines = content.splitlines()
             if len(lines) > 1:
                 try:
                    parsed_data = json.loads('\n'.join(lines[1:]))
                 except:
                    pass
        
        if parsed_data is not None:
            return parsed_data
            
        # Fallback: Return raw content as error object if not valid JSON
        # This handles Volatility error messages stored in .json files
        return {"error": "Invalid JSON output", "raw_output": content}

    except Exception as e:
        return {"error": f"Error reading file: {str(e)}"}

def process_recover_fs(output_dir):
    """
    Reads the unstructured output of linux.pagecache.RecoverFs and 
    builds a structured JSON tree representing the file system.
    Also extracts recovered_fs.tar.gz so files are readable by MCP.
    """
    import tarfile

    json_path = os.path.join(output_dir, "linux.pagecache.RecoverFs_output.json")
    if not os.path.exists(json_path):
        return

    # Extract the recoverfs tarball if it exists so the APIs can serve it
    tar_path = os.path.join(output_dir, "recovered_fs.tar.gz")
    extract_dir = os.path.join(output_dir, "recovered_fs")
    if os.path.exists(tar_path) and not os.path.exists(extract_dir):
        try:
            os.makedirs(extract_dir, exist_ok=True)
            # Python's tarfile silently refuses to extract absolute paths on 3.9
            # We use the system's robust tar binary which handles `tar: Removing leading /` automatically
            import subprocess
            subprocess.run(["tar", "-xzf", tar_path, "-C", extract_dir], check=True)
        except Exception as e:
            print(f"[ERROR] Failed to extract recovered_fs.tar.gz via system tar: {e}")

    try:
        data = clean_and_parse_json(json_path)
        if not data or isinstance(data, dict):
            # If it's a dict, it's either an error or not the expected array list of nodes
            return

        # data is a list of nodes: [{"__class__": ..., "TreeDepth": 0, "Inode": ..., "FilePath": "/"}, ...]
        
        # Build a tree structure
        # Use a dictionary to quickly find nodes by their full path
        tree = {"name": "/", "path": "/", "type": "directory", "children": []}
        
        # We also want to map paths to the actual extracted files on disk.
        # Volatility usually extracts them to `output_dir` with naming like "file.<inode>.<address>..."
        # We will scan the dir and map inodes to files.
        extracted_files = {}
        for filename in os.listdir(output_dir):
            if filename.startswith("file."):
                 parts = filename.split('.')
                 if len(parts) >= 2:
                     inode_str = parts[1]
                     if inode_str.isdigit():
                         # Inode might be 0x hex in json, but decimal in filename? 
                         extracted_files[str(int(inode_str))] = filename

        nodes_by_path = {"/": tree}
        
        for item in data:
            file_path = item.get("FilePath")
            if not file_path or file_path == "/": continue
            
            # Remove leading slash for processing
            clean_path = file_path.strip("/")
            parts = clean_path.split("/")
            
            current_node = tree
            current_path = ""
            
            for i, part in enumerate(parts):
                current_path = current_path + "/" + part if current_path else "/" + part
                
                # Check if this node already exists at this level
                found = False
                children_list = current_node.get("children", [])
                for child in children_list:
                    if child["name"] == part:
                        current_node = child
                        found = True
                        break
                
                if not found:
                    is_leaf = (i == len(parts) - 1)
                    new_node = {
                        "name": part,
                        "path": current_path,
                        "type": "file" if is_leaf else "directory",
                    }
                    
                    if is_leaf:
                       new_node["inode"] = item.get("Inode")
                       inode_id = str(item.get("Inode"))
                       # Check if we have an extracted file for this
                       if inode_id in extracted_files:
                           new_node["extracted_file"] = extracted_files[inode_id]
                           # Add size if file exists on disk
                           full_ext_path = os.path.join(output_dir, extracted_files[inode_id])
                           if os.path.exists(full_ext_path):
                               new_node["size"] = os.path.getsize(full_ext_path)
                               
                    if not is_leaf:
                        new_node["children"] = []
                        
                    if "children" not in current_node:
                        current_node["children"] = []
                    current_node["children"].append(new_node)
                    current_node = new_node

        # Save tree back directly over the "raw" JSON or as a new file.
        # Overwriting is easiest so the frontend just requests the module as usual.
        with open(json_path, 'w') as f:
            json.dump([tree], f, indent=2) # Wrap in array for consistency
            
        print(f"[DEBUG] process_recover_fs completed for {output_dir}")
            
    except Exception as e:
        import traceback
        print(f"[ERROR] Failed to process RecoverFs:\n{traceback.format_exc()}")

def cleanup_timeouts():
    """Marks scans running for > 1 hour as failed (timeout)."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        one_hour_ago = time.time() - 3600
        
        # Find tasks that are 'running' and older than 1 hour
        c.execute("SELECT uuid FROM scans WHERE status='running' AND created_at < ?", (one_hour_ago,))
        stale_scans = c.fetchall()
        
        if stale_scans:
            print(f"Cleaning up {len(stale_scans)} stale scans...")
            c.execute("UPDATE scans SET status='failed', error='Timeout (>1h)' WHERE status='running' AND created_at < ?", (one_hour_ago,))
            conn.commit()
            
        conn.close()
    except Exception as e:
        print(f"Error cleaning up timeouts: {e}")
