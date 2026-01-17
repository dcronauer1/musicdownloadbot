import os
import json
import sys
import shutil

def _default_config():
    return {  #config["directory_settings"]["temp_directory"] is set on run, not saved to the file
        "bot_settings": {
            "BOT_TOKEN": "your_token_here",
            "whitelist": ["your_discord_id_here","another_id_here"]
        },
        "download_settings": {
            "music_directory": "/var/music",
            "file_type": "opus",
            "file_extension": ".opus",
            "default_cover_size": "1200",
            "yt_dlp_path": "{program_dir}/yt-dlp"
        },
        "directory_settings":{
            "keep_perms_consistent": True,
            "music_file_perms": 664,
            "music_directory_perms": 775,
            "group": "None",
            "auto_update": True,
            "temp_directory": "{program_dir}/temp"
        },
        "musicbrainz": {
            "app_name": "YourMusicBot",
            "contact_email": "tempemail1732218732931@gmail.com"
        },
        "dev":{
            "debug": False
        }
    }

def replace_placeholders(config, before_list, after_list):
    """
    Recursively replace multiple placeholders in dict and list values.

    Args:
        config (dict): dictionary to process
        before_list (list[str]): list of strings to replace
        after_list (list[str]): list of replacement strings

    Example:
        replace_placeholders(config, ['a', 'b'], ['A', 'B'])
    """
    if isinstance(config, dict):
        for k, v in config.items():
            config[k] = replace_placeholders(v, before_list, after_list)
    elif isinstance(config, list):
        return [replace_placeholders(v, before_list, after_list) for v in config]
    elif isinstance(config, str):
        for before, after in zip(before_list, after_list):
            config = config.replace(before, after)
    return config

def validate_config(config, default_config):
    """Validate the config file, filling in missing fields with defaults."""
    updated = False
    for key, default_value in default_config.items():
        if key not in config:
            print(f"Missing '{key}', adding default.")
            config[key] = default_value
            updated = True
        elif isinstance(default_value, dict):
            if not isinstance(config[key], dict):
                config[key] = default_value
                updated = True
            else:
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

    # Create default config if it doesnt exist
    default_config = _default_config()
    config_path = os.path.join(program_dir,"config.json")
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        print("Config file created. Please fill it out and restart.")
        sys.exit(0)

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in config.json.")
        sys.exit(0)

    if validate_config(config, default_config):
        print("Updating config with missing defaults.")
        config_path_old = os.path.join(program_dir,"config.json.old")
        shutil.copy(config_path, config_path_old)
        print("Backup created: config.json.old")

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        print("Config updated")
        sys.exit(1)

    #check for missing critical configs 
    should_exit = False
    if config["bot_settings"]["BOT_TOKEN"] == "your_token_here":
        print("You need to set your Discord bot token in config.json")
        should_exit = True

    if config["bot_settings"]["whitelist"] == ["your_discord_id_here","another_id_here"]:
        print("Whitelist is default. Either enter your Discord id, or make it blank.\n⚠️WARNING: If left blank, anyone can run commands with your bot")
        should_exit = True
    # Keep only entries that can be converted to int
    config["bot_settings"]["whitelist"] = [
        int(x) for x in config["bot_settings"]["whitelist"]
        if isinstance(x, (int, str)) and str(x).isdigit()
    ]

    #replace placeholders
    replace_placeholders(config, ["{program_dir}"], [program_dir])

    # Validate critical paths and files 
    replace_placeholders(default_config, ["{program_dir}"], [program_dir])

    keys = [("download_settings", "music_directory"),("directory_settings", "temp_directory")]
    for section, option in keys:    #check critical directories
        path = config[section][option]
        if not os.path.exists(path):
            default_path = default_config[section][option]
            if path == default_path:
                # Default path missing → create it
                try:
                    os.makedirs(path, mode=0o775, exist_ok=True)
                    print(f"Created default {option} directory: {path}")
                except OSError as e:
                    print(f"ERROR: Failed to create {option} directory: {e}")
                    should_exit=True
            else:
                print(f"ERROR: {option} not default and path does not exist: {path}")
                should_exit=True
        #Check if directory is accessible
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK) or not os.path.isdir(path):
            print(f"{path} is not accessible or isn't a directory. Please fix")
            should_exit = True

    if should_exit: sys.exit(0) #give all errors and then exit

    if config["dev"]["debug"]:
        print(config)
    return config

# Load config when imported
config = initialize_config()
