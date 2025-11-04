# LinkedIn Job Scraper

A Python application that scrapes LinkedIn posts for job opportunities, classifies them using AI models, and exports the results to CSV. The project uses Selenium for web scraping and Ollama for AI-powered classification of hiring posts and profile names.

## Features

- **Automated LinkedIn Scraping**: Scrapes LinkedIn posts based on search queries
- **AI Classification**: Uses Ollama models to classify:
  - Hiring-related posts (job postings, recruitment)
  - Profile names (Indian names classification)
- **CSV Export**: Saves scraped and classified data to CSV files
- **Continuous Operation**: Runs in a loop with configurable intervals until keyboard interrupt
- **Background Operation**: Works even when Firefox window is in the background (uses JavaScript scrolling)
- **GPU/CPU Detection**: Automatically detects and reports whether Ollama is using GPU or CPU
- **Configurable**: Customizable search terms, scroll attempts, intervals, and logging

## Prerequisites

- **Python 3.11+**: The project requires Python 3.11 or higher
- **uv**: Fast Python package installer and resolver ([Installation Guide](https://github.com/astral-sh/uv))
- **Firefox Browser**: Required for Selenium WebDriver automation
- **LinkedIn Account**: Valid LinkedIn credentials for scraping

### Installing uv

If you don't have `uv` installed, you can install it using:

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip
pip install uv
```

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd linkedin_scrape
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```
   
   This will:
   - Create a virtual environment (if it doesn't exist)
   - Install all project dependencies from `pyproject.toml`
   - Generate a lock file (`uv.lock`)

3. **Verify installation:**
   ```bash
   uv run python --version
   ```

## Configuration

### Environment Variables (Optional)

You can set the following environment variables to override default configuration:

- `LINKEDIN_EMAIL`: Your LinkedIn email address
- `LINKEDIN_PASSWORD`: Your LinkedIn password
- `LINKEDIN_LOG_LEVEL`: Logging level (default: `INFO`)
- `LINKEDIN_LOG_FORMAT`: Log format string

Example:
```bash
export LINKEDIN_EMAIL="your.email@example.com"
export LINKEDIN_PASSWORD="your_password"
export LINKEDIN_LOG_LEVEL="DEBUG"
```

### Configuration File

Default settings can be modified in `src/config/settings.py`:
- `SEARCH_TEXT`: Default search query (default: "Data Scientist")
- `MAX_SCROLL_ATTEMPTS`: Maximum scroll attempts (default: 20)
- `MAX_POSTS`: Maximum posts to collect (default: 10)
- `MODEL_NAME`: Ollama model name (default: "deepseek-r1:1.5b")

## Usage

### Running the Application

The main entry point requires three mandatory arguments:

```bash
uv run python src/main.py \
  --email "your.email@example.com" \
  --password "your_password" \
  --search_text "Data Scientist"
```

### Command-Line Arguments

- `--email` (required): LinkedIn email address
- `--password` (required): LinkedIn password
- `--search_text` (required): Search query text for LinkedIn posts
- `--max_scroll_attempts` (optional): Maximum number of scroll attempts (defaults to config value)
- `--interval` (optional): Hours to wait between iterations (default: 1.0 hour). Supports decimal values (e.g., 0.5 for 30 minutes, 2.0 for 2 hours)

### Example Usage

```bash
# Basic usage with all required arguments (runs every hour by default)
uv run python src/main.py \
  --email "user@example.com" \
  --password "secure_password" \
  --search_text "Machine Learning Engineer"

# With custom scroll attempts
uv run python src/main.py \
  --email "user@example.com" \
  --password "secure_password" \
  --search_text "Python Developer" \
  --max_scroll_attempts 30

# Run every 30 minutes (0.5 hours)
uv run python src/main.py \
  --email "user@example.com" \
  --password "secure_password" \
  --search_text "Data Scientist" \
  --interval 0.5

# Run every 2 hours
uv run python src/main.py \
  --email "user@example.com" \
  --password "secure_password" \
  --search_text "Software Engineer" \
  --interval 2.0

# Run every 15 minutes with custom scroll attempts
uv run python src/main.py \
  --email "user@example.com" \
  --password "secure_password" \
  --search_text "DevOps Engineer" \
  --max_scroll_attempts 50 \
  --interval 0.25
```

### What Happens When You Run

The application runs in a **continuous loop** until you press `Ctrl+C` (keyboard interrupt). Each iteration:

1. **Initialization**: 
   - Sets up Firefox WebDriver (works in background)
   - Detects Ollama GPU/CPU usage
   - Logs into LinkedIn
   - Navigates to search results

2. **Scraping**:
   - Scrolls through LinkedIn posts using JavaScript (works even when window is in background)
   - Extracts post content, URLs, and profile names
   - Filters for job-related posts

3. **Classification**:
   - Uses Ollama model to classify posts as hiring-related (binary: 0 or 1)
   - Classifies profile names (binary: 0 or 1 for Indian names)

4. **Export**:
   - Appends results to `linkedin_jobs.csv` with columns:
     - `content`: Post content
     - `url`: Post URL
     - `profile_name`: Profile name of the poster
     - `hiring_post`: Classification result (0 or 1)
     - `names_classification`: Name classification result (0 or 1)

5. **Wait Period**:
   - Waits for the specified interval (default: 1 hour)
   - Shows progress logs every 10 minutes
   - Repeats the cycle

**To Stop**: Press `Ctrl+C` to gracefully shutdown the application.

## Project Structure

```
linkedin_scrape/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── scrape.py            # LinkedIn scraping logic
│   ├── ollama_setup.py      # Ollama model setup and inference
│   ├── dataclass.py         # Pydantic models for classification
│   └── config/
│       └── settings.py      # Configuration settings
├── pyproject.toml           # Project dependencies and metadata
├── uv.lock                  # Locked dependency versions
└── README.md               # This file
```

## Ollama Model Setup

The application automatically handles Ollama installation and model setup:

- **Automatic Installation**: Detects OS and installs Ollama if not present
- **Model Download**: Automatically pulls the specified model (`deepseek-r1:1.5b` by default)
- **GPU/CPU Detection**: Automatically detects and reports whether Ollama is using GPU (CUDA/Metal/ROCm) or CPU
- **No Manual Setup Required**: All setup is handled during first run

Note: On Windows, Ollama installation must be done manually. Download from [ollama.com](https://ollama.com).

### GPU Detection

The application automatically detects GPU usage:
- **NVIDIA GPUs**: Detects CUDA support via `nvidia-smi`
- **Apple Silicon/AMD (macOS)**: Detects Metal support
- **AMD GPUs (Linux)**: Detects ROCm support
- **CPU Fallback**: Uses CPU if no GPU is detected

Device information is logged during initialization.

## Output

The application generates a CSV file (`linkedin_jobs.csv`) with the following structure:

| content | url | profile_name | hiring_post | names_classification |
|---------|-----|--------------|-------------|---------------------|
| Post text... | https://... | John Doe | 1 | 0 |
| Post text... | https://... | Priya Sharma | 0 | 1 |

## Troubleshooting

### Firefox WebDriver Issues

- Ensure Firefox is installed and accessible in your PATH
- If you encounter WebDriver errors, try updating Firefox to the latest version
- **Background Operation**: The scraper uses JavaScript scrolling, so it works even when the Firefox window is in the background. You can continue using your computer while it runs.

### Ollama Installation Issues

- On macOS/Linux: The script will attempt automatic installation
- On Windows: Download and install Ollama manually from [ollama.com](https://ollama.com)
- Verify Ollama is running: `ollama --version`

### LinkedIn Login Issues

- Ensure your credentials are correct
- LinkedIn may require additional verification (2FA, captcha)
- Check if your account is temporarily restricted

### Dependencies Issues

If you encounter dependency conflicts:

```bash
# Sync dependencies again
uv sync

# Or recreate the virtual environment
rm -rf .venv
uv sync
```

## Development

### Running in Development Mode

```bash
# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows

# Run with debug logging
LINKEDIN_LOG_LEVEL=DEBUG uv run python src/main.py \
  --email "your.email@example.com" \
  --password "your_password" \
  --search_text "Data Scientist"
```

### Adding Dependencies

To add a new dependency:

```bash
uv add package-name
```

To add a development dependency:

```bash
uv add --dev package-name
```

## License

This project is for educational and research purposes. Please ensure compliance with LinkedIn's Terms of Service and applicable data protection regulations when using this tool.

## Notes

- **Rate Limiting**: The application includes built-in delays to avoid overwhelming LinkedIn's servers
- **Continuous Operation**: The application runs in a loop until you press `Ctrl+C`. Make sure to stop it when done.
- **Background Operation**: The Firefox window can run in the background - the scraper uses JavaScript scrolling which doesn't require window focus
- **Data Accumulation**: Results are appended to the CSV file, so each run adds new data without overwriting previous results
- **Ethical Use**: Use responsibly and respect LinkedIn's robots.txt and terms of service
- **Data Privacy**: Be mindful of privacy implications when scraping and storing LinkedIn data

