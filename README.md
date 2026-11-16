# Personal Assistant

A Streamlit chat assistant powered by Groq. It can search Google with SearchApi and look up current weather with the free Open-Meteo APIs.

## Requirements

- Python 3.10 or newer
- Git
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

2. In the project root, copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Open `.env` and replace the placeholder values with your own keys:

   ```dotenv
   GROQ_API_KEY=your_groq_api_key
   SEARCHAPI_API_KEY=your_searchapi_api_key
   ```

   `GROQ_API_KEY` is used by the Groq chat model. `SEARCHAPI_API_KEY` enables Google web search. Weather lookups use Open-Meteo and do not require an API key.

Keep `.env` private. It is excluded from Git; never commit or share your real API keys. If a key has been exposed, revoke it with its provider and create a replacement.

## Run the app

From the project root, with the virtual environment activated:

```powershell
streamlit run Apps/Assistent.py
```

Streamlit prints a local URL in the terminal (usually `http://localhost:8501`). Open it in your browser to use the assistant.

## Troubleshooting

- If the app reports a missing API key, confirm `.env` is in the project root, the variable names match exactly, and the values are valid.
- If a Python module is missing, activate the virtual environment and run `python -m pip install -r requirement.txt` again.
