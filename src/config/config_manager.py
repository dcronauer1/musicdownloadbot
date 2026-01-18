import os
import json
import sys
import shutil

CONFIG = None

def _default_config():
    return {  #CONFIG["directory_settings"]["temp_directory"] is set on run, not saved to the file
        "bot_settings": {
            "BOT_TOKEN": "your_token_here",
            "whitelist": ["your_discord_id_here","another_id_here"]
        },
        "download_settings": {
            "music_directory": "/var/music",
            "file_type": "opus",
            "file_extension": ".opus",
            "default_cover_size": "1200"
        },
        "directory_settings":{
            "keep_perms_consistent": True,
            "music_file_perms": 664,
            "music_directory_perms": 775,
            "user_group": "None",
            "auto_update": True,
            "auto_update_ytdlp": True,
            "temp_directory": "{program_dir}/temp",
            "yt_dlp_path": "{program_dir}/yt-dlp"
        },
        "musicbrainz": {
            "app_name": "YourMusicBot",
            "contact_email": "tempemail1732218732931@gmail.com"
        },
        "dev":{
            "verbose": False    #TODO need to implement still
        }
    }

#TODO make this modular (maybe)
def validate_specific_configs(config, default_config, verbose=True):
    """check for missing critical configs and validate directories."""
    errors = []

    if config["bot_settings"]["BOT_TOKEN"] == "your_token_here":
        errors.append("You need to set your Discord bot token in config.json")

    if config["bot_settings"]["whitelist"] == ["your_discord_id_here","another_id_here"]:
        errors.append("Whitelist is default. Either enter your Discord id, or make it blank.\n⚠️WARNING: If left blank, anyone can run commands with your bot")

    # Keep only entries that can be converted to int
    config["bot_settings"]["whitelist"] = [
        int(x) for x in config["bot_settings"]["whitelist"]
        if isinstance(x, (int, str)) and str(x).isdigit()
    ]
    
    keys = [("download_settings", "music_directory"),("directory_settings", "temp_directory")]
    for section, option in keys:    #check critical directories
        path = config[section][option]
        if not os.path.exists(path):
            default_path = default_config[section][option]
            if path == default_path:
                # Default path missing → create it
                try:
                    os.makedirs(path, mode=0o775, exist_ok=True)
                    if verbose: 
                        print(f"Created default {option} directory: {path}")
                except OSError as e:
                    errors.append(f"ERROR: Failed to create {option} directory: {e}")
            else:
                errors.append(f"ERROR: {option} not default and path does not exist: {path}")
        #Check if directory is accessible
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK) or not os.path.isdir(path):
            errors.append(f"{path} is not accessible or isn't a directory. Please fix")

    if errors: 
        raise ConfigError("\n".join(errors)) #give all errors and then exit

class ConfigError(Exception):
    """should terminate program without restarting"""
    pass

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
        return {k: replace_placeholders(v, before_list, after_list) for k, v in config.items()}
    elif isinstance(config, list):
        return [replace_placeholders(v, before_list, after_list) for v in config]
    elif isinstance(config, str):
        for before, after in zip(before_list, after_list):
            config = config.replace(before, after)
        return config
    return config

def validate_config(config, default_config, verbose=True):
    """Validate the config file, filling in missing fields with defaults."""
    updated = False
    for key, default_value in default_config.items():
        if key not in config:
            if verbose: 
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
            if verbose: 
                print(f"'{key}' is None, setting to default: {default_value}")
            config[key] = default_value
            updated = True
    return updated

def initialize_config(verbose=True):
    """Load and validate the config file."""
    global CONFIG
    if CONFIG is not None:
        return CONFIG  # already initialized

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
        raise ConfigError("Config file created. Please fill it out and restart.")

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        raise ConfigError("Error: Invalid JSON format in config.json.")

    # Validate critical paths and files 
    if validate_config(config, default_config, verbose=verbose):
        if verbose: #backup config 
            print("Updating config with missing defaults.")
        config_path_old = os.path.join(program_dir,"config.json.old")
        shutil.copy(config_path, config_path_old)
        if verbose:
            print("Backup created: config.json.old")

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        if verbose:
            print("Config updated")

    #replace program_dir placeholder
    config = replace_placeholders(config, ["{program_dir}"], [program_dir])
    default_config = replace_placeholders(default_config, ["{program_dir}"], [program_dir])

    validate_specific_configs(config, default_config, verbose=verbose)

    if config["dev"]["verbose"] and verbose:
        print(config)
    CONFIG = config
    return CONFIG