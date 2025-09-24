# Flowers Telegram Bot

This is a Telegram bot for a flower shop. It allows users to browse products, place orders, and provide feedback. It also includes an admin panel for managing cities and products.

## Setup

1.  **Clone the repository** (or download the files).

2.  **Install dependencies**:
    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Set the Bot Token**:
    This bot requires a Telegram Bot API token. You need to set it as an environment variable named `BOT_TOKEN`.

    On Linux/macOS:
    ```bash
    export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN_HERE"
    ```

    On Windows (Command Prompt):
    ```bash
    set BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN_HERE"
    ```

    On Windows (PowerShell):
    ```bash
    $env:BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN_HERE"
    ```

    Replace `"YOUR_TELEGRAM_BOT_TOKEN_HERE"` with your actual token from BotFather.

## Running the Bot

Once you have installed the dependencies and set the environment variable, you can run the bot with:

```bash
python flowers.py
```

The bot will start polling for updates. You should see a log message in your terminal indicating that the bot has started successfully.
