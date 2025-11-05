import discord
import asyncio
import os
import re
import json
import grp
import sys
import requests
import shutil
import tempfile
import subprocess
from config.config_manager import config
from typing import Optional

FILE_EXTENSION = config["download_settings"]["file_extension"]
TEMP_DIRECTORY = config["directory_settings"]["temp_directory"]
MUSIC_DIRECTORY = config["download_settings"]["music_directory"]

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
    Applies consistent permissions to all files and directories in MUSIC_DIRECTORY
    based on the configuration settings.

    :return: False if failed, True if success
    """
    if not config["directory_settings"]["keep_perms_consistent"]:
        return False
    
    # Convert permissions to octal
    file_perms = int(str(config["directory_settings"]["file_perms"]), 8)
    dir_perms = int(str(config["directory_settings"]["directory_perms"]), 8)
    target_group = config["directory_settings"]["group"]

    if target_group is None or target_group == "None":
        gid = os.getegid()
    else:
        try:
            gid = grp.getgrnam(target_group).gr_gid
        except KeyError:
            print(f"Group {target_group} not found")
            return False

    for root, dirs, files in os.walk(MUSIC_DIRECTORY):
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

def save_music_tree():
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

    tree_lines = _build_and_format_tree(MUSIC_DIRECTORY)

    file_path = os.path.join(TEMP_DIRECTORY,"tree.txt")

    with open(file_path, 'w') as f:
        f.write('\n'.join(tree_lines))

    return file_path

def update_files(update_self=config["directory_settings"]["auto_update"]):
    """Function to run on start, and periodically"""

    update_release("yt-dlp/yt-dlp","yt-dlp",config["download_settings"]["yt_dlp_path"])

    if update_self:
        update_release("dcronauer1/musicdownloadbot","musicdownloadbot",restart_if_updated=True)
    else:
        #TODO prompt user to update IF there is an update (also send them the version changes)
        pass
    
    #check if ytdlp exists
    ytdlp_path = config["download_settings"]["yt_dlp_path"]
    if not os.path.exists(ytdlp_path):
        print(f"ERROR: yt-dlp does not exist: {ytdlp_path}")
        sys.exit(1)

def update_release(repo: str, asset_name: str, output_path=None, restart_if_updated=False) -> bool:
    """
    Check if there is a new release for the given GitHub repo and asset,
    and download it if it is newer than the last version.

    Args:
        repo: GitHub repository in the form 'owner/repo'
        asset_name: Name of the asset file to download
        output_path: Where the asset goes. MUST include /asset_name at the end. None for program_dir/asset_name

    Returns:
        True if the asset was updated, False otherwise
    """
    version_file = os.path.join(TEMP_DIRECTORY, f"{repo.replace('/', '_')}_version.txt")

    if output_path is None:
        # Determine output path depending on whether running from frozen executable
        program_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(program_dir, asset_name)

    # Get latest release info from GitHub API
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(api_url)
    response.raise_for_status()
    release = response.json()
    latest_version = release["tag_name"]

    # Check if we already have this version
    if os.path.exists(version_file) and os.path.isfile(output_path):
        with open(version_file, "r") as f:
            current_version = f.read().strip()
        if current_version == latest_version:
            print(f"{repo} is up to date ({latest_version})")
            return False

    # Find the asset in the release
    asset = next((a for a in release["assets"] if a["name"] == asset_name), None)
    if not asset:
        raise Exception(f"Asset '{asset_name}' not found in the latest release of {repo}.")

    # Download asset content
    download_url = asset["browser_download_url"]
    print(f"Downloading {asset_name} from {repo} version {latest_version}")
    # stream the download to avoid partial-write execution problems and to conserve memory
    r = requests.get(download_url, stream=True)
    r.raise_for_status()

    # Save to a temporary file (so we don't overwrite the running binary)
    # Use same directory as output to keep move atomic on same FS when possible.
    tmp_dir = os.path.dirname(output_path) or "."
    with tempfile.NamedTemporaryFile(delete=False, dir=tmp_dir, prefix=asset_name + "_") as tmp_file:
        # write in streaming chunks to avoid memory issues
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                tmp_file.write(chunk)
        # flush and sync to ensure the file is fully written to disk before we try to execute/move it
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        tmp_path = tmp_file.name
    # ensure downloaded file is executable
    try:
        st = os.stat(tmp_path)
        os.chmod(tmp_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        # best-effort chmod; we'll attempt again after move if needed
        pass

    # Update version file
    with open(version_file, "w") as f:
        f.write(latest_version)

    print(f"{asset_name} downloaded to temporary path {tmp_path}")

    if restart_if_updated:
        # Replace old binary with the downloaded one and then exit.
        # The service manager is expected to restart the program.
        try:
            # Use shutil.move to handle cross-filesystem moves as well.
            shutil.move(tmp_path, output_path)
            try:
                os.chmod(output_path, 0o755)
            except Exception:
                pass
            print(f"{asset_name} updated to {latest_version} at {output_path}")
            print("Update applied; exiting so the service manager can restart the program.")
        except Exception as e:
            # If move fails, keep the tmp file (for debugging) and raise
            print(f"Failed to replace binary: {e}")
            raise
        # Exit as failure so service will restart it
        sys.exit(1)

    # If not restarting immediately, replace in place
    shutil.move(tmp_path, output_path)
    try:
        os.chmod(output_path, 0o755)
    except Exception:
        pass
    print(f"{asset_name} updated to {latest_version} at {output_path}")
    return True