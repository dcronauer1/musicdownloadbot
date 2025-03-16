import subprocess
import os
import json
import difflib
from config_manager import config
from utils import ask_confirmation
import re

# Retrieve settings from the JSON configuration
YT_DLP_PATH = config["download_settings"]["yt_dlp_path"]
BASE_DIRECTORY = config["download_settings"]["base_directory"]

def load_known_list(filename):
    """Load a JSON list from a file, or return an empty list if file does not exist."""
    if not os.path.exists(filename):
        return []
    with open(filename, "r") as f:
        return json.load(f)

def save_known_list(filename, lst):
    """Save the list as JSON to a file."""
    with open(filename, "w") as f:
        json.dump(lst, f, indent=4)

def check_and_update_artist(artist: str) -> str:
    """
    Check if the artist is known (case-insensitive). If a close match exists,
    suggest it (and automatically use it), otherwise add the new artist to the list.
    """
    filename = os.path.join(BASE_DIRECTORY, "artists.json")
    known_artists = load_known_list(filename)
    
    # lowercase for easier matching
    lower_artist = artist.lower()
    lower_known = {a.lower(): a for a in known_artists}
    
    #check for direct match
    for index,items in enumerate(lower_known):
        if lower_artist == items:
            return known_artists[index] #match found, so return the stored version
        
    # Use fuzzy matching to look for close matches.
    matches = difflib.get_close_matches(lower_artist, lower_known.keys(), n=1, cutoff=0.8)
    if matches:
        suggestion = lower_known[matches[0]]
        print(f"Artist '{artist}' not found. Did you mean '{suggestion}'? Using '{suggestion}'.")
        return suggestion
    else:
        print(f"Artist '{artist}' is new. Adding it to the known list.")

        ####### Need to add a user confirmation for this!!

        known_artists.append(artist)
        save_known_list(filename, known_artists)
        return artist

def check_and_update_tags(tags: str) -> list:
    """
    Check each tag against the known list. Each tag is converted to Title Case.
    If a close match exists, use that suggestion; otherwise, add the new tag.
    """
    filename = os.path.join(BASE_DIRECTORY, "tags.json")
    known_tags = load_known_list(filename)
    updated_tags = []
    lower_known = {tag.lower(): tag for tag in known_tags}
    
    for tag in tags:
        # Convert tag to Title Case.
        tag_normalized = tag.strip().title()
        lower_tag = tag_normalized.lower()
        if lower_tag in lower_known:
            updated_tags.append(lower_known[lower_tag])
        else:
            matches = difflib.get_close_matches(lower_tag, lower_known.keys(), n=1, cutoff=0.8)
            if matches:
                suggestion = lower_known[matches[0]]
                print(f"Tag '{tag_normalized}' not found. Did you mean '{suggestion}'? Using '{suggestion}'.")
                updated_tags.append(suggestion)
            else:
                
                ####### Need to add a user confirmation for this!!

                print(f"Tag '{tag_normalized}' is new. Adding it to the known list.")
                known_tags.append(tag_normalized)
                updated_tags.append(tag_normalized)
    save_known_list(filename, known_tags)
    return updated_tags

def get_video_info(video_url: str) -> dict:
    """Fetch video info (as JSON) using yt-dlp and return the parsed dictionary. Used for defaulting parameters"""
    yt_dlp_info_cmd = [YT_DLP_PATH, "--dump-single-json", video_url]
    try:
        result = subprocess.run(yt_dlp_info_cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        return info
    except subprocess.CalledProcessError as e:
        print(f"Error fetching video info: {e.returncode}")
        return {}

def download_audio(interaction, video_url: str, output_name: str = None, artist_name: str = None, tags: list = None) -> str:
    """
    Downloads a YouTube video as ALAC audio with embedded metadata.
    
    If output_name or artist_name is not provided, uses video title and uploader respectively.
    Tags (if provided) are checked against known tags and added as a comma-separated metadata field.
    
    :param video_url: URL of the YouTube video.
    :param output_name: Base name for the output file. Defaults to video title.
    :param artist_name: Artist name to embed in metadata. Defaults to video uploader.
    :param tags: tags in a string.
    :return: The path to the downloaded audio file (.m4a) or None if error.
    """
    # Get video info to set defaults if needed
    info = {}
    if not output_name or not artist_name:
        info = get_video_info(video_url)
    
    if not output_name:
        output_name = info.get("title", "Untitled")
    if not artist_name:
        artist_name = info.get("uploader", "Unknown")
    
    # Check against known lists. (authors and tags)
    artist_name = check_and_update_artist(artist_name)
    if tags:
        # Split the tags by commas and strip extra spaces
        tags_list = [tag.strip() for tag in re.split(r"[,;]", tags) if tag.strip()]
        
        # Process and update tags list
        tags_list = check_and_update_tags(tags_list)

        # Join them back into a properly formatted string
        tags_str = "; ".join(tags_list) #m4a uses semicolins
    else:
        tags_str = None

    # Construct the output file template; yt-dlp will append the proper extension.
    output_file_template = os.path.join(BASE_DIRECTORY, f"{output_name}.%(ext)s")
    
    # Build the metadata postprocessor args:
    meta_args = f"-metadata artist='{artist_name}'"
    #meta_args += f" -metadata title='{output_name}'"

    if tags_str:
        meta_args += f" -metadata genre='{tags_str}'"
    
    #confirm selection
    if ask_confirmation(interaction, meta_args) == False:
        return

    #Update yt-dlp
    yt_dlp_cmd = [
        YT_DLP_PATH, "-U"
    ]
    print("Updating yt-dlp.")
    try:
        subprocess.run(yt_dlp_cmd, check=True)
        print("Update complete.")
        # The converted file should be .m4a
    except subprocess.CalledProcessError as e:
        print(f"Error: yt-dlp failed with code {e.returncode}")
        return None
    #Download video
    yt_dlp_cmd = [
        YT_DLP_PATH, "-x", "--audio-format", "alac",
        "--embed-thumbnail", "--add-metadata", "--embed-chapters",
        "--postprocessor-args", meta_args,
        "-o", output_file_template,
        video_url
    ]
    
    print("Downloading audio...")
    try:
        print(f"full debug command: {yt_dlp_cmd}")   #for debugging
        subprocess.run(yt_dlp_cmd, check=True)
        print("Download complete.")
        # The converted file should be .m4a
        return os.path.join(BASE_DIRECTORY, f"{output_name}.m4a")
    except subprocess.CalledProcessError as e:
        print(f"Error: yt-dlp failed with code {e.returncode}")
        return None
