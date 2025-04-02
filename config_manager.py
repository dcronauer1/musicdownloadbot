import os
import json
import sys
import shutil

DEFAULT_CONFIG = {
    "bot_settings": {
        "BOT_TOKEN": "[your-token-here]"
    },
    "download_settings": {
        "yt_dlp_path": "/path/to/yt-dlp",
        "base_directory": "/path/to/music",
        "file_type": "alac",
        "file_extension": ".m4a"
    }
}

def validate_config(config, default_config):
    """
    Validate the config file, filling in missing fields with defaults.
    """
    updated = False

    for key, default_value in default_config.items():
        if key not in config:
            print(f"Missing '{key}', adding default.")
            config[key] = default_value
            updated = True
        elif isinstance(default_value, dict):
            updated = validate_config(config[key], default_value) or updated
        elif config[key] is None:
            print(f"'{key}' is None, setting to default: {default_value}")
            config[key] = default_value
            updated = True

    return updated

def initialize_config():
    """Load and validate the config file."""
    if not os.path.exists("config.json"):
        with open("config.json", "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print("Config file created. Please fill it out and restart.")
        sys.exit(0)

    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in config.json.")
        sys.exit(1)

    if validate_config(config, DEFAULT_CONFIG):
        print("Updating config with missing defaults.")

        shutil.copy("config.json", "config.json.old")
        print("Backup created: config.json.old")

        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)

        print("Config updated. Restarting required.")
        sys.exit(0)

    return config

# Load config when imported
config = initialize_config()
