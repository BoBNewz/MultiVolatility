# MultiVolatility ⚡️

**Analyze memory dumps faster than ever with Volatility2 and Volatility3 in parallel.**

MultiVolatility (`multivol`) is a powerful CLI wrapper that orchestrates memory forensics using Docker. It parallizes execution across multiple CPU cores, dramatically reducing the time required to run full scan suites on `windows` or `linux` memory dumps.

![Demo](https://raw.githubusercontent.com/BoBNewz/MultiVolatility/00d7b95cba1e35c9a4810f3e145bddc324e24628/CLI/demo.gif)
## Features

- **Parallel Execution**: runs multiple Volatility plugins simultaneously using your machine's full CPU power.
- **Hybrid Support**: Seamlessly supports both **Volatility 2** and **Volatility 3**.
- **Containerized**: Runs all analysis in Docker containers—no complex dependency hell or Python 2/3 conflicts on your host.
- **Smart Caching**: Automatically manages symbol downloads and caching to prevent redundant network requests.
- **Flexible Output**: Supports both textual reports and structured JSON output for integration with other tools (like the MultiVol Web UI).

## Prerequisites

1.  **Docker**: Ensure Docker Desktop (or Engine) is installed and running.
    *   [Install Docker](https://docs.docker.com/get-docker/)
2.  **Python 3.6+**

## Installation

You can install `multivol` directly from PyPI:

```bash
pip install multivol
```

### From Source

Alternatively, you can clone the repository and install it locally:

```bash
git clone https://github.com/BoBNewz/MultiVolatility.git
cd MultiVolatility/CLI
pip install .
```

This installs the `multivol` command available system-wide.

### Building the Docker Images
Before running the tool, you must build the analysis images:

```bash
# Build Volatility 2
docker build Dockerfiles/volatility2/ -t volatility2:latest

# Build Volatility 3
docker build Dockerfiles/volatility3/ -t volatility3:latest
```

## Usage

The basic syntax is:

```bash
multivol [vol2|vol3] --dump <path_to_dump> --image <docker_image> [options]
```

### Examples

**Run a standard Windows analysis with Volatility 3:**
```bash
multivol vol3 --dump memdump.raw --image volatility3:latest --windows --light
```

**Run a full analysis on a Linux dump:**
```bash
multivol vol3 --dump linux_dump.wem --image volatility3:latest --linux --full
```

**Use Volatility 2 with a specific profile:**
```bash
multivol vol2 --dump box_win7.raw --image volatility2:latest --profile Win7SP1x64 --windows --light
```

### Options

| Option | Description |
| :--- | :--- |
| `--dump` | **Required.** Path to the memory dump file. |
| `--image` | **Required.** Name of the Docker image to use (e.g., `volatility3:latest`). |
| `--windows` / `--linux` | **Required.** Specify the OS of the memory dump. |
| `--light` | Run a curated set of essential plugins (Fast). |
| `--full` | Run the comprehensive suite of all available plugins (Slow). |
| `--commands` | Run a specific comma-separated list of plugins (e.g., `pslist,filescan`). |
| `--processes` | Limit the number of concurrent Docker containers (Default: CPU Count). |
| `--api` | Start the tool in API mode for Web UI integration. |

## Web Integration

MultiVol comes with a companion Web Interface for visualizing results and creating scans (Process Trees, File Browsers, etc.).

To use the CLI as a backend for the Web UI:
 (optional).
 
Run `multivol --api`. or use the `docker-compose.yml`

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
