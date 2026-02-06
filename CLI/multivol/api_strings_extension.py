
@app.route('/results/<uuid>/strings', methods=['GET'])
def get_strings_content(uuid):
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 1000, type=int)
    query = request.args.get('q', '')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = scan['output_dir']
    strings_file = os.path.join(output_dir, "strings_output.txt")
    
    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404

    content = []
    total_lines = 0

    import subprocess

    if query:
        # Search mode - simple grep (limited to first 1000 matches to avoid overflow)
        try:
            # -i for case insensitive, -n for line numbers, -m for max count
            # We use a max count to prevent massive memory usage
            cmd = ['grep', '-i', '-n', '-m', str(limit), query, strings_file]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Format: "line_num:content"
            content = result.stdout.splitlines()
            total_lines = len(content) # Not real total of file, but total matches found (up to limit)
            
        except Exception as e:
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        # Pagination mode
        try:
            # Get total lines using wc -l
            wc_cmd = ['wc', '-l', strings_file]
            wc_res = subprocess.run(wc_cmd, stdout=subprocess.PIPE, text=True)
            total_lines = int(wc_res.stdout.split()[0])
            
            # Use sed to extract range efficiently
            start_line = (page - 1) * limit + 1
            end_line = start_line + limit - 1
            
            sed_cmd = ['sed', '-n', f'{start_line},{end_line}p', strings_file]
            sed_res = subprocess.run(sed_cmd, stdout=subprocess.PIPE, text=True, errors='replace')
            content = sed_res.stdout.splitlines()
            
        except Exception as e:
            return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    return jsonify({
        "content": content,
        "total": total_lines,
        "page": page,
        "limit": limit
    })

@app.route('/results/<uuid>/strings/download', methods=['GET'])
def download_strings(uuid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = scan['output_dir']
    strings_file = os.path.join(output_dir, "strings_output.txt")
    
    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404
        
    return send_file(strings_file, as_attachment=True, download_name=f"strings_{uuid}.txt")
