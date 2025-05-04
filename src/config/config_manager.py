import os
import json
import sys
import shutil

DEFAULT_CONFIG = {  #config["directory_settings"]["temp_directory"] is set on run, not saved to the file
    "bot_settings": {
        "BOT_TOKEN": "[your-token-here]"
    },
    "download_settings": {
        "yt_dlp_path": "/path/to/yt-dlp",
        "base_directory": "/path/to/music",
        "file_type": "opus",
        "file_extension": ".opus",
        "default_cover_size": "1200"
    },
    "directory_settings":{
        "keep_perms_consistent": True,
        "file_perms": 664,
        "directory_perms": 775,
        "group": "sambashare"
    },
    "musicbrainz": {
        "app_name": "YourMusicBot",
        "contact_email": "tempemail1732218732931@gmail.com"
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
    
    # Validate critical paths
    required_paths = {
        "yt-dlp": config["download_settings"]["yt_dlp_path"],
        "base directory": config["download_settings"]["base_directory"]
    }
    for name, path in required_paths.items():
        if not os.path.exists(path):
            print(f"ERROR: {name} path does not exist: {path}")
            sys.exit(1)
    
    # Add temp directory to config
    if getattr(sys, 'frozen', False):  # PyInstaller bundle
        program_dir = os.path.dirname(sys.executable)
    else:  # Running as Python script
        program_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(program_dir, "temp")
    config["directory_settings"]["temp_directory"] = temp_dir
    print(f"temp_dir: {temp_dir}")

    # Create directory
    if not os.path.exists(temp_dir):
        try:
            os.makedirs(temp_dir, exist_ok=False)
        except OSError as e:
            print(f"ERROR: Failed to create temp directory: {e}")

    return config

# Load config when imported
config = initialize_config()
