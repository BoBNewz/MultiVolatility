import os
import requests
from fastmcp import FastMCP

# Initialisation du serveur MCP
mcp = FastMCP("MultiVol MCP")

# Configuration cible
BASE_URL = os.getenv("TARGET_URL", "http://api")
PORT = os.getenv("TARGET_PORT", "5001")


def build_url(path: str) -> str:
    return f"{BASE_URL}:{PORT}{path}"


@mcp.tool()
def get_scans() -> dict:
    """
    Get all scans from the server.

    You can get the following attributes:
    - The dump name
    - The OS of the memory dump
    - The image name
    - The date of the scan creation
    - The output directory of the scan
    - The UUID of the scan
    - The status of the scan
    - The mode of the scan (light or full)

    This function could be used if you need to get the UUID to list run modules.
    """
    response = requests.get(build_url("/scans"))
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_scan_modules(uuid: str) -> dict:
    """
    Get all modules of a specific scan.

    For each module, you can get the following attributes:
    - If there is some errors
    - The module name
    - The status of the module

    This function could be used to get the module names.
    """
    response = requests.get(build_url(f"/scan/{uuid}/modules"))
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_results(uuid: str, module: str) -> dict:
    """
    Get the results of a module of a specific scan. 

    The returned file is a JSON and it is an output from Volatility2 or Volatility3.
    """
    response = requests.get(
        build_url(f"/results/{uuid}"),
        params={"module": module}
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    mcp.run(transport="stdio", log_level="error")