from flask import Blueprint, jsonify, request
import docker
import os
import textwrap
import json
import logging
from multivol.api_server.utils import resolve_host_path
from multivol.api_server.config import BASE_DIR

docker_bp = Blueprint('docker_bp', __name__)

@docker_bp.route('/list_images', methods=['GET'])
def list_images():
    try:
        client = docker.from_env()
        images = client.images.list()
        volatility_images = []
        for img in images:
            if img.tags:
                for tag in img.tags:
                    if "volatility" in tag:
                        volatility_images.append(tag)
        return jsonify({"images": list(set(volatility_images))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@docker_bp.route('/volatility3/plugins', methods=['GET'])
def list_volatility_plugins():
    image = request.args.get('image')
    if not image:
         return jsonify({"error": "Missing 'image' query parameter"}), 400
         
    try:
        script_content = """
            import sys
            # Ensure we can find the package in typical locations
            if "/volatility3" not in sys.path:
                sys.path.insert(0, "/volatility3")
            
            from volatility3 import framework
            import volatility3.plugins
            import json

            try:
                failures = framework.import_files(volatility3.plugins, ignore_errors=True)
                plugins = framework.list_plugins()  # dict: {"windows.pslist.PsList": <class ...>, ...}
                
                output = {
                    "count": len(plugins),
                    "plugins": sorted(list(plugins.keys())),
                    "failures": sorted([str(f) for f in failures]) if failures else []
                }
                print(json.dumps(output))
            except Exception as e:
                import traceback
                print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        """
        script_content = textwrap.dedent(script_content)
        
        # Write script to outputs dir so we can mount it
        output_dir = os.path.join(BASE_DIR, "outputs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        script_path = os.path.join(output_dir, "list_plugins_script.py")
        with open(script_path, "w") as f:
            f.write(script_content)
            
        # Resolve host path for Docker volume
        host_script_path = resolve_host_path(script_path)
        
        client = docker.from_env()
        
        # Run container
        logging.debug(f"running list_plugins on image {image}")
        container = client.containers.run(
            image=image,
            entrypoint="python3", 
            command="/list_plugins.py",
            volumes={
                host_script_path: {'bind': '/list_plugins.py', 'mode': 'ro'}
            },
            working_dir="/volatility3", # Set working dir to repo root avoids some path issues
            environment={"PYTHONPATH": "/volatility3"}, # Explicitly set pythonpath
            stderr=True,
            remove=True
        )
        
        # Parse output
        raw_output = container.decode('utf-8')
        try:
            # Output should be mainly JSON
            lines = raw_output.splitlines()
            # It might have stderr logs, so look for JSON
            json_line = None
            for line in reversed(lines):
                if line.strip().startswith('{'):
                    json_line = line
                    break
            
            if json_line:
                data = json.loads(json_line)
                return jsonify(data)
            else:
                 return jsonify({"error": "No JSON output found", "raw": raw_output}), 500
        except Exception:
             return jsonify({"error": "Failed to parse script output", "raw": raw_output}), 500

    except Exception as e:
        logging.error(f"List plugins failed: {e}")
        return jsonify({"error": str(e)}), 500
