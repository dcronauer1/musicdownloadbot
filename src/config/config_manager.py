import os
import json
import sys
import shutil

DEFAULT_CONFIG = {  #config["directory_settings"]["temp_directory"] is set on run, not saved to the file
    "bot_settings": {
        "BOT_TOKEN": "[your-token-here]"
    },
    "download_settings": {
        "music_directory": "{program_dir}/music",
        "file_type": "opus",
        "file_extension": ".opus",
        "default_cover_size": "1200",
        "yt_dlp_path": "{program_dir}/yt-dlp"
    },
    "directory_settings":{
        "keep_perms_consistent": True,
        "file_perms": 664,
        "directory_perms": 775,
        "group": "None",
        "auto_update": True
    },
    "musicbrainz": {
        "app_name": "YourMusicBot",
        "contact_email": "tempemail1732218732931@gmail.com"
    }
}

def replace_placeholders(config, before_list, after_list):
    """
    Recursively replace multiple placeholders in dict values.

    Args:
        config (dict): dictionary to process
        before_list (list[str]): list of strings to replace
        after_list (list[str]): list of replacement strings

    Example:
        replace_placeholders(config, ['a', 'b'], ['A', 'B'])
    """
    if len(before_list) != len(after_list):
        raise ValueError("before_list and after_list must have the same length")

    for k, v in config.items():
        if isinstance(v, dict):
            replace_placeholders(v, before_list, after_list)
        elif isinstance(v, str):
            for before, after in zip(before_list, after_list):
                if before in v:
                    v = v.replace(before, after)
            config[k] = v

def validate_config(config, default_config):
    """Validate the config file, filling in missing fields with defaults."""
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
    if getattr(sys, 'frozen', False):  # PyInstaller bundle
        program_dir = os.path.dirname(sys.executable)
    else:  # Running as Python script
        program_dir = os.path.dirname(os.path.abspath(__file__))

    # Create default config if not exists
    config_path = os.path.join(program_dir,"config.json")
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print("Config file created. Please fill it out and restart.")
        sys.exit(0)

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in config.json.")
        sys.exit(1)

    if validate_config(config, DEFAULT_CONFIG):
        print("Updating config with missing defaults.")
        config_path_old = os.path.join(program_dir,"config.json.old")
        shutil.copy(config_path, config_path_old)
        print("Backup created: config.json.old")

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        print("Config updated. Restart required.")
        sys.exit(0)

    #replace placeholders
    replace_placeholders(config, ["{program_dir}"], [program_dir])

    # Validate critical paths and files 
    temp_config = DEFAULT_CONFIG
    replace_placeholders(temp_config, ["{program_dir}"], [program_dir])
    for key in ["music_directory"]:
        path = config["download_settings"][key]
        if not os.path.exists(path):
            default_path = temp_config["download_settings"][key]
            if path == default_path:
                # Default path missing → create it
                try:
                    os.makedirs(path, exist_ok=True)
                    print(f"Created default {key} directory: {path}")
                except OSError as e:
                    print(f"ERROR: Failed to create {key} directory: {e}")
                    sys.exit(1)
            else:
                print(f"ERROR: {key} path does not exist: {path}")
                sys.exit(1)

    # Add temp directory
    temp_dir = os.path.join(program_dir, "temp")
    config["directory_settings"]["temp_directory"] = temp_dir
    os.makedirs(temp_dir, exist_ok=True)

    return config

# Load config when imported
config = initialize_config()
