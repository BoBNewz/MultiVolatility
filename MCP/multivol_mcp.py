import os
import requests
from fastmcp import FastMCP
from fastmcp.server.auth.auth import TokenVerifier, AccessToken
import re
import json

API_TOKEN = os.getenv("API_TOKEN")
MCP_TOKEN = os.getenv("MCP_TOKEN", "my-super-secret-token")
BASE_URL = os.getenv("TARGET_URL", "http://api")
PORT = os.getenv("TARGET_PORT", "5001")

class StaticTokenAuth(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == MCP_TOKEN:
            return AccessToken(
                token=token,
                client_id="MCP",
                scopes=[],
                expires_at=None,
                resource="http://127.0.0.1:8000/mcp"
            )
        return None

def build_url(path: str) -> str:
    return f"{BASE_URL}:{PORT}{path}"

# 1. Set up a Session for connection pooling and default headers
session = requests.Session()
session.headers.update({"Authorization": f"Bearer {API_TOKEN}"})
TIMEOUT = 30 # seconds

def safe_request(method: str, url: str, **kwargs) -> dict:
    """Helper to handle requests gracefully so the AI gets clean errors instead of stack traces."""
    try:
        response = session.request(method, url, timeout=TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Backend API request failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": "Backend API returned invalid JSON."}

mcp = FastMCP("MultiVol MCP", auth=StaticTokenAuth(), list_page_size=50)

@mcp.tool()
def search_multivol_results(uuid: str, module: str, regex_pattern: str, max_matches: int = 50, context_lines: int = 0) -> dict:
    """
    Search through ALL results of a scan module using a Regular Expression.
    
    CRITICAL INSTRUCTIONS FOR AI:
    - Use this tool INSTEAD of get_results when looking for specific IoCs.
    - Provide a valid Python regex string (e.g., '192\.168\.\d+\.\d+' or '(?i)malware\.exe').
    - For the 'strings' module, use context_lines (0-100) to show surrounding lines around each match (like grep -C).
    """
    try:
        pattern = re.compile(regex_pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}. Please fix."}

    # Cap context_lines at 100
    context_lines = min(max(context_lines, 0), 100)

    chunk_size = 2000
    offset = 0
    page = 1
    matched_results = []
    total_scanned = 0
    
    # 2. True Pagination: Loop until we hit max_matches or run out of data
    while len(matched_results) < max_matches:
        if module == "strings":
            params = {"limit": chunk_size, "page": page, "q": regex_pattern}
            if context_lines > 0:
                params["context"] = context_lines
            data = safe_request("GET", build_url(f"/results/{uuid}/strings"), params=params)
        else:
            data = safe_request("GET", build_url(f"/results/{uuid}"), params={"module": module, "limit": chunk_size, "offset": offset})
            
        if "error" in data:
            return data # Surface backend errors immediately

        results_list = data if isinstance(data, list) else data.get("results", data.get("content", []))
        if not results_list:
            break # No more data from backend
            
        total_scanned += len(results_list)
        
        for item in results_list:
            if pattern.search(json.dumps(item)):
                matched_results.append(item)
                if len(matched_results) >= max_matches:
                    break

        offset += chunk_size
        page += 1

    return {
        "metadata": {
            "regex_used": regex_pattern,
            "context_lines": context_lines if module == "strings" else "N/A",
            "total_matches_returned": len(matched_results),
            "rows_scanned": total_scanned,
            "status": "Capped at max_matches" if len(matched_results) >= max_matches else "Scanned all available rows"
        },
        "matches": matched_results
    }

@mcp.tool()
def get_multivol_scans() -> dict:
    """Get all scans from the server. Returns UUIDs, OS, image names, and status."""
    return {"scans": safe_request("GET", build_url("/scans"))}

@mcp.tool()
def get_multivol_scan_modules(uuid: str) -> dict:
    """Get all modules of a specific scan."""
    return {"modules": safe_request("GET", build_url(f"/scan/{uuid}/modules"))}

@mcp.tool()
def get_multivol_results(uuid: str, module: str, limit: int = 50, offset: int = 0) -> dict:
    """
    Get the results of a module of a specific scan. 

    CRITICAL INSTRUCTIONS FOR AI: 
    If you pass limit=0, it defaults to 50. 
    If 'has_more' is true in metadata, call this tool again with 'next_offset'.
    """
    if limit <= 0 or limit > 100:
        limit = 50

    if module == "strings":
        page = (offset // limit) + 1 if limit > 0 else 1
        data = safe_request("GET", build_url(f"/results/{uuid}/strings"), params={"limit": limit, "page": page})
    else:
        data = safe_request("GET", build_url(f"/results/{uuid}"), params={"module": module, "limit": limit, "offset": offset})

    if isinstance(data, dict) and "error" in data:
        return data

    results_list = data if isinstance(data, list) else data.get("results", [])
    has_more = len(results_list) >= limit

    return {
        "metadata": {
            "current_offset": offset,
            "limit_applied": limit,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
            "SYSTEM_NOTE": "If has_more is true, call get_results again with the next_offset."
        },
        "results": data
    }

@mcp.tool()
def list_multivol_linux_recovered_files(uuid: str, offset: int = 0, limit: int = 100, search: str = "") -> dict:
    """
    Lists files that were successfully extracted by the recoverFS module (LINUX ONLY).
    Use `offset` and `limit` to paginate through the list.
    Use `search` to filter files matching a specific string or extension (e.g. search=".txt" or search="passwd").
    """
    data = safe_request("GET", build_url(f"/results/{uuid}/fs/list"))
    if "error" in data:
        return data
        
    files = data.get("files", [])
    if search:
        search_lower = search.lower()
        files = [f for f in files if search_lower in f.lower()]
        
    paginated = files[offset:offset+limit]
    has_more = (offset + limit) < len(files)
    
    return {
        "metadata": {
            "total_files": len(files),
            "current_offset": offset,
            "limit": limit,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
            "search_filter": search
        },
        "files": paginated
    }

@mcp.tool()
def list_multivol_windows_recovered_files(uuid: str, offset: int = 0, limit: int = 100, search: str = "") -> dict:
    """
    Lists files that are available for recovery on Windows (MemProcFS + FileScan).
    This tool combines results from MemProcFS.FileList (highly reliable if session active)
    and windows.filescan.FileScan (static results from previous analysis).
    """
    merged_files = {}

    # 1. Try MemProcFS.FileList results
    # We use limit=0 to fetch all, as we'll paginate manually after merging
    memproc_data = safe_request("GET", build_url(f"/memprocfs/{uuid}/files"), params={"limit": 0})
    if not isinstance(memproc_data, dict) or "error" not in memproc_data:
        files = memproc_data.get("results", []) if isinstance(memproc_data, dict) else []
        for f in files:
            name = f.get("Name", "UNKNOWN")
            merged_files[name] = {
                "name": name,
                "vfs_path": f.get("VfsPath"),
                "size": f.get("Size"),
                "source": f.get("Source", "MemProcFS"),
                "is_downloadable": True if f.get("VfsPath") else False
            }

    # 2. Try windows.filescan.FileScan results
    filescan_data = safe_request("GET", build_url(f"/results/{uuid}"), params={"module": "windows.filescan.FileScan", "limit": 0})
    # get_results returns a list or {"results": [...]}
    filescan_results = filescan_data if isinstance(filescan_data, list) else filescan_data.get("results", []) if isinstance(filescan_data, dict) else []
    
    for f in filescan_results:
        name = f.get("Name", "UNKNOWN")
        if name in merged_files:
            # Update existing with offset info
            merged_files[name]["offset"] = f.get("Offset")
        else:
            merged_files[name] = {
                "name": name,
                "offset": f.get("Offset"),
                "source": "FileScan",
                "is_downloadable": False # FileScan results don't provide direct VfsPath access without MemProcFS
            }

    # 3. Filter and Paginate
    all_files = list(merged_files.values())
    if search:
        search_lower = search.lower()
        all_files = [f for f in all_files if search_lower in f["name"].lower()]

    # Sort so results are consistent
    all_files.sort(key=lambda x: x["name"])
    
    paginated = all_files[offset:offset+limit]
    has_more = (offset + limit) < len(all_files)

    return {
        "metadata": {
            "total_files": len(all_files),
            "current_offset": offset,
            "limit": limit,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
            "search_filter": search,
            "note": "Files with 'is_downloadable: true' can be downloaded using download_multivol_windows_recovered_file"
        },
        "files": paginated
    }

@mcp.tool()
def view_multivol_linux_recovered_file(uuid: str, file_path: str, regex_pattern: str = "", max_matches: int = 50) -> dict:
    """
    Search or paginate through a specific file extracted by recoverFS (LINUX ONLY).
    Pass a regex_pattern to grep through the file. Leave it empty to read the first max_matches lines.
    """
    chunk_size = 2000
    page = 1
    matched_results = []
    total_scanned = 0
    
    while len(matched_results) < max_matches:
        params = {"path": file_path, "limit": chunk_size, "page": page}
        if regex_pattern:
            params["q"] = regex_pattern
            
        data = safe_request("GET", build_url(f"/results/{uuid}/fs/view"), params=params)
        
        if "error" in data:
            return data
            
        results_list = data.get("content", [])
        if not results_list:
            break
            
        total_scanned += len(results_list)
        
        for item in results_list:
            matched_results.append(item)
            if len(matched_results) >= max_matches:
                break
                
        page += 1

    return {
        "metadata": {
            "file_read": file_path,
            "regex_used": regex_pattern if regex_pattern else "NONE",
            "lines_returned": len(matched_results),
            "lines_scanned": total_scanned,
            "status": "Capped at max_matches" if len(matched_results) >= max_matches else "EOF reached"
        },
        "content": matched_results
    }


@mcp.tool()
def get_multivol_linux_download_link(uuid: str, file_path: str) -> dict:
    """
    Get a download link (curl command) for a file extracted by recoverFS (LINUX ONLY).
    """
    import urllib.parse
    encoded_path = urllib.parse.quote(file_path)
    
    get_params = f"/results/{uuid}/fs/download?path={encoded_path}"
    
    file_name = os.path.basename(file_path)
    output_name = f"{uuid[:8]}_{file_name}"
    
    curl_command = f'curl -sSf -H "Authorization: Bearer {API_TOKEN}" "[YOUR_MULTIVOL_API_URL]{get_params}" -o "{output_name}"'
    
    return {
        "success": True,
        "message": "Execute the provided curl_command replacing [YOUR_MULTIVOL_API_URL] to download the linux file locally.",
        "curl_command": curl_command,
        "expected_output_file": output_name
    }

@mcp.tool()
def download_multivol_windows_recovered_file(uuid: str, vfs_path: str) -> dict:
    """
    Get a download link (curl command) for a Windows file extracted by MemProcFS.
    The 'vfs_path' should be taken from list_multivol_windows_recovered_files.
    MemProcFS sidecar session MUST be running for this to work.
    """
    import urllib.parse
    encoded_path = urllib.parse.quote(vfs_path)
    
    get_params = f"/memprocfs/{uuid}/download?path={encoded_path}"
    
    file_name = os.path.basename(vfs_path)
    output_name = f"{uuid[:8]}_{file_name}"
    
    curl_command = f'curl -sSf -H "Authorization: Bearer {API_TOKEN}" "[YOUR_MULTIVOL_API_URL]{get_params}" -o "{output_name}"'
    
    return {
        "success": True,
        "message": "Ensure MemProcFS is started. Use the provided curl_command replacing [YOUR_MULTIVOL_API_URL] to download the windows file locally.",
        "curl_command": curl_command,
        "expected_output_file": output_name
    }

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)