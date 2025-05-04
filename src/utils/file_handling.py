import discord
import asyncio
import os
import re
import json
import grp
import sys
from config.config_manager import config
from typing import Optional

FILE_EXTENSION = config["download_settings"]["file_extension"]
TEMP_DIRECTORY = config["directory_settings"]["temp_directory"]

def get_entries_from_json(filename) -> str:
    """function to return all entries from a json file"""
    if not os.path.exists(filename):
        return "file doesn't exist"
    
    try:
        with open(filename) as file:
            data = json.load(file)
        return data
    except json.JSONDecodeError:
        return "file exists but contains invalid JSON"

def find_file_case_insensitive(directory, filename):
    """function to find files of the same name, with different casing, and return the file in use
    
    :return: either fullPath, or None: nothing was found
    """
    #first check if exact casing exists already
    fullPath = os.path.join(directory,filename)
    if os.path.exists(fullPath):
        return fullPath
    #next check if same name, different casing exists
    for file in os.listdir(directory):
        if file.lower() == filename.lower():
            return os.path.join(directory, file)
    return None

def apply_directory_permissions():
    """
    Applies consistent permissions to all files and directories in BASE_DIRECTORY
    based on the configuration settings.

    :return: False if failed, True if success
    """
    if not config["directory_settings"]["keep_perms_consistent"]:
        return False

    base_dir = config["download_settings"]["base_directory"]
    
    # Convert permissions to octal
    file_perms = int(str(config["directory_settings"]["file_perms"]), 8)
    dir_perms = int(str(config["directory_settings"]["directory_perms"]), 8)
    target_group = config["directory_settings"]["group"]

    try:
        gid = grp.getgrnam(target_group).gr_gid
    except KeyError:
        print(f"Group {target_group} not found")
        return False

    for root, dirs, files in os.walk(base_dir):
        for name in dirs + files:
            path = os.path.join(root, name)
            try:
                # Set group ownership first
                os.chown(path, -1, gid)  # -1 preserves current UID
                
                # Set permissions
                mode = dir_perms if os.path.isdir(path) else file_perms
                os.chmod(path, mode)
                
            except PermissionError as e:
                print(f"⚠️Permission denied on {path}: {e}")
            except Exception as e:
                print(f"⚠️Error processing {path}: {e}")
    print("✅Updated file permissions successfully\n")
    return True

def save_music_tree(base_directory):
    """
    Function to recursively build a tree of the given directory.
    Excludes .txt files.
    Saves as tree.txt in the temp directory (directory main is being ran from)

    :return file: path/to/tree.txt
    
    """
    def _build_and_format_tree(directory, indent=0):
        lines = []
        for entry in sorted(os.scandir(directory), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.is_dir():
                lines.append('  ' * indent + f'{entry.name}/')
                lines.extend(_build_and_format_tree(entry.path, indent + 1))
            elif not entry.name.endswith('.txt'):
                lines.append('  ' * indent + f'{entry.name}')
        return lines

    tree_lines = _build_and_format_tree(base_directory)

    file_path = os.path.join(TEMP_DIRECTORY,"tree.txt")

    with open(file_path, 'w') as f:
        f.write('\n'.join(tree_lines))

    return file_path