# Email Classification Agent

AI-powered email classification and organization using OpenAI. Automatically classifies emails into smart categories and applies Gmail labels.

## Features

- **Real Gmail Integration** - Direct Gmail API access with OAuth
- **AI Classification** - GPT-4o-mini for fast, accurate categorization
- **Auto-Labeling** - Automatically creates and applies Gmail labels
- **Smart Categories** - 8 predefined categories (2FA, Work, Newsletter, etc.)
- **Beautiful TUI** - Interactive terminal interface with real-time logs
- **CLI Mode** - Perfect for automation and cron jobs
- **Async Processing** - Efficient concurrent email classification

## Quick Start

### Install

```bash
git clone <repository-url>
cd email-classifier-agent
uv sync
```

Or with pip:

```bash
pip install -e .
```

### Configure

Create `.env` file:

```bash
# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=2000

# Gmail
EMAIL_PROVIDER=gmail
GMAIL_CREDENTIALS_PATH=config/credentials.json
GMAIL_TOKEN_PATH=config/token.json
```

### Gmail Setup

1. **Get OAuth credentials** from [Google Cloud Console](https://console.cloud.google.com):
   - Create project → Enable Gmail API
   - Create OAuth 2.0 Desktop App credentials
   - Download JSON → save as `config/credentials.json`

2. **Authenticate** (first run):
   ```bash
   python3 << 'EOF'
   from google.auth.transport.requests import Request
   from google.oauth2.credentials import Credentials
   from google_auth_oauthlib.flow import InstalledAppFlow
   from pathlib import Path
   
   creds_file = Path('config/credentials.json')
   token_file = Path('config/token.json')
   
   flow = InstalledAppFlow.from_client_secrets_file(
       creds_file, ['https://mail.google.com/'], redirect_uri='http://localhost:8080/'
   )
   creds = flow.run_local_server(port=8080, open_browser=True)
   
   with open(token_file, 'w') as f:
       f.write(creds.to_json())
   print("Authentication complete!")
   EOF
   ```

### Run

```bash
# Classify emails
uv run python -m main classify --provider gmail --limit 10

# Interactive TUI
uv run python -m main tui

# Check config
uv run python -m main config-check
```

**Note:** After `uv sync`, you can also use `email-classifier` command directly if installed globally.

## Configuration

### Categories

Edit `config/categories.yaml` to customize categories:

```yaml
categories:
  - name: "Work"
    description: "Professional emails and meetings"
    keywords: ["meeting", "project", "deadline"]
    priority_boost: 1
```

### Model Options

- **gpt-4o-mini** (default): Fast, cost-effective (~$0.15/$0.60 per 1M tokens)
- **gpt-4o**: More powerful (~$2.50/$10 per 1M tokens)
- **gpt-5-nano**: Advanced reasoning (~$0.10/$0.30 per 1M tokens, slower)

## How It Works

1. **Fetches** emails from Gmail inbox
2. **Classifies** each email with OpenAI GPT-4o-mini
3. **Creates** Gmail labels for categories (if needed)
4. **Applies** labels automatically to emails
5. **Shows** beautiful statistics and breakdown

## Example Output

```
Classification Results

            Summary            
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric             ┃  Value ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Processed    │     10 │
│ Successful         │     10 │
│ Average Confidence │  89.2% │
│ Processing Time    │ 45.3s  │
└────────────────────┴────────┘

Categories Breakdown
  Newsletter: 4
  2FA: 2
  Work: 3
  Receipts: 1
```

## Project Structure

```
email-classifier-agent/
├── agent/              # Core classification logic
├── config/             # Settings, prompts, categories
├── mcp_clients/        # Gmail/Outlook API clients
├── models/             # Pydantic schemas
├── ui/                 # Textual TUI interface
├── main.py             # CLI entry point
└── pyproject.toml      # Project dependencies
```

## Requirements

- Python 3.10+
- OpenAI API key
- Gmail OAuth credentials
- `uv` (recommended) or `pip`

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.
