# Home Assistant MCP Server

This repository contains a minimal **MCP (Micro‑service Communication Protocol)** server that connects to a Home Assistant instance via the `homeassistant_api` Python client.  The server introspects the client’s public API and emits a JSON description of the available methods, parameters, and documentation.  The JSON is written to **stdout** so that an MCP‑compatible client can consume it and expose the Home Assistant functionality as a remote service.

## Features
- Loads configuration from a `.env` file (or environment variables).
- Validates that `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` are present.
- Uses `inspect` to discover all public methods of the `homeassistant_api.Client`.
- Generates example values for each parameter (redacting sensitive data).
- Sanitises the output to avoid leaking tokens.
- Prints a JSON payload that can be consumed by any MCP client.

## Setup
For macOS and Linux users, a `setup.sh` script is provided to create a virtual environment and install all required Python packages.  The script also copies the example environment file `env.sample` to `.env`.

```bash
# Run the setup script
./setup.sh
```

The `env.sample` file contains placeholder values.  Copy it to `.env` and replace the placeholders with your Home Assistant URL and long‑lived access token.  **Do not share that token with anyone else.**

## Usage
If the setup script hasn't been run, create your python virtual environment and install python package requirements
```bash
pip install -r requirements.txt
```
Create a new `.env` file (you can do this by copying the env.sample in the repository), and put the URL of your **Home Assistant** instance and the long lived token.
```bash
HOME_ASSISTANT_URL=https://my.homeassistant.local
HOME_ASSISTANT_TOKEN=YOUR_LONG_LIVED_ACCESS_TOKEN
```
Finally run the server
```bash
python home_assistant_mcp_server.py
```

The script will output a JSON object to stdout.  An MCP client can read this output and expose the Home Assistant API over the MCP protocol.

## Caveats
- **Work in progress** – the project is still under active development and may contain bugs or incomplete features.
- **Not production ready** – use at your own risk.  The server does not implement authentication, rate‑limiting, or advanced error handling.
- **Sensitive data** – the script redacts tokens in the example payload, but be careful when sharing the output.

Feel free to fork, contribute, or use this as a starting point for building your own MCP‑based Home Assistant integration.
