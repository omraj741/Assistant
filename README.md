# Personal Assistant

A Streamlit chat assistant powered by Groq. It can search Google with SearchApi and look up current weather with the free Open-Meteo APIs.

## Requirements

- Python 3.10 or newer
- Git
- A running PostgreSQL database
- MCP Toolbox for Databases (Windows binary)
- A Groq API key
- A SearchApi API key (for web search)

## Installation

1. Clone the repository and open a terminal in the project folder:

   ```powershell
   git clone https://github.com/omraj741/Assistant.git
   cd Assistant
   ```

2. Create and activate a virtual environment:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate the environment again.

3. Install the project dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirement.txt
   ```

## Configure API keys

1. Create your own keys:
   - Groq: [Groq Console API Keys](https://console.groq.com/keys)
   - SearchApi: [SearchApi](https://www.searchapi.io/)

2. Create a `.env` file in the project root:

   ```powershell
   New-Item .env -ItemType File
   ```

3. Open `.env` and replace the placeholder values with your own keys:

   ```dotenv
   GROQ_API_KEY=your_groq_api_key
   SEARCHAPI_API_KEY=your_searchapi_api_key
   TOOLBOX_URL=http://127.0.0.1:5000
   ```

   `GROQ_API_KEY` is used by the Groq chat model. `SEARCHAPI_API_KEY` enables Google web search. `TOOLBOX_URL` is optional and defaults to the URL shown above. Weather lookups use Open-Meteo and do not require an API key.

Keep `.env` private. It is excluded from Git; never commit or share your real API keys. If a key has been exposed, revoke it with its provider and create a replacement.

## Run the app

PostgreSQL requests require MCP Toolbox. Download the Windows AMD64 binary from the [MCP Toolbox releases](https://github.com/googleapis/mcp-toolbox/releases), or use this PowerShell command from the project root:

```powershell
$VERSION = "1.17.0"
curl.exe -o toolbox.exe "https://storage.googleapis.com/mcp-toolbox-for-databases/v$VERSION/windows/amd64/toolbox.exe"
```

Open a PowerShell terminal in the project root, set the connection values for your PostgreSQL database, and start the Toolbox server:

```powershell
$env:POSTGRES_HOST = "localhost"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_DATABASE = "your_database"
$env:POSTGRES_USER = "your_user"
$env:POSTGRES_PASSWORD = "your_password"
.\toolbox.exe --config "Apps/postgres_tools.yaml"
```

Keep that terminal running. In a second terminal, activate the virtual environment and start Streamlit:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run Apps/Assistent.py
```

Streamlit prints a local URL in the terminal (usually `http://localhost:8501`). Open it in your browser to use the assistant. The Toolbox connection variables must be set in the terminal where its server runs; they are not read from the app's `.env` file.

## Troubleshooting

- If the app reports a missing API key, confirm `.env` is in the project root, the variable names match exactly, and the values are valid.
- If a Python module is missing, activate the virtual environment and run `python -m pip install -r requirement.txt` again.
