import os
import json
import difflib
import re
import shutil
from config.config_manager import config
from utils.core import run_command
from utils.discord_helpers import ask_confirmation
from utils.metadata import get_audio_duration,apply_thumbnail_to_file

# Retrieve settings from the JSON configuration
YT_DLP_PATH = config["download_settings"]["yt_dlp_path"]
BASE_DIRECTORY = config["download_settings"]["base_directory"]
FILE_TYPE = config["download_settings"]["file_type"]
FILE_EXTENSION = config["download_settings"]["file_extension"]


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

async def check_and_update_artist(artist: str, interaction) -> str:
    """
    Check if the artist is known (case-insensitive). If a close match exists,
    suggest it (and automatically use it), otherwise add the new artist to the list.
    """
    filename = "artists.json"
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
        print(f"Artist '{artist}' is new. Add it to the known list?")
        user_output=f"Artist '{artist}' is new. Add it to the known list?\n"
        if (await ask_confirmation(interaction, user_output)) == False: #confirm if user wants to add artist to list
            return False

        known_artists.append(artist)
        save_known_list(filename, known_artists)
        return artist

async def check_and_update_tags(tags: str, interaction) -> list:
    """
    Check each tag against the known list. Each tag is converted to Title Case.
    If a close match exists, use that suggestion; otherwise, add the new tag.
    """
    filename = "tags.json"
    known_tags = load_known_list(filename)
    updated_tags = []
    lower_known = {tag.lower(): tag for tag in known_tags}
    user_output = ""
    trying_to_gen_new_tag = False
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
                user_output += (f"Tag '{tag_normalized}' not found. Did you mean '{suggestion}'? Using '{suggestion}'.\n") #output this to user
                updated_tags.append(suggestion)
            else: 
                #if here, then user must confirm the addition of new tag(s)
                trying_to_gen_new_tag=True
                
                print(f"Tag '{tag_normalized}' is new. Add it to the known list?")
                user_output += (f"Tag '{tag_normalized}' is new. Add it to the known list?\n") #output this to user
                known_tags.append(tag_normalized)
                updated_tags.append(tag_normalized)
    if trying_to_gen_new_tag:
        if (await ask_confirmation(interaction, user_output)) == False:
            return False
    save_known_list(filename, known_tags)
    return updated_tags

async def get_video_info(video_url: str) -> tuple[dict,str]:
    """Fetch video info (as JSON) using yt-dlp and return the parsed dictionary. Used for defaulting parameters

    :return dict: desired info from video (title, uploader, upload_date)
    :return error_str: None if no error, string containing error if error

    """
    yt_dlp_info_cmd = (
        f"{YT_DLP_PATH} --print 'title' --print 'uploader' --print 'upload_date' {video_url}"
    )
    returncode, output, stderr = await run_command(yt_dlp_info_cmd, verbose=True)

    if returncode == 0:
        try:
            title, uploader, upload_date = output.strip().split("\n", 2)
            return {
                "title": title,
                "uploader": uploader,
                "upload_date": upload_date,
            }, None
        except ValueError:
            error_str = f"Error: Unexpected output format.\nRaw output:\n{output}"
            print(error_str)
            return {},error_str
    error_str=f"Error: Failed to fetch video info.\nStderr:\n{stderr}"
    print(error_str)
    return {},error_str

async def download_audio(interaction, video_url: str, type: str, output_name: str = None, artist_name: str = None, tags: list = None,
                        album: str = None, addtimestamps: bool = None) -> tuple:
    """
    Downloads a YouTube video as FILE_EXTENSION audio with embedded metadata.
    
    If output_name or artist_name is not provided, uses video title and uploader respectively.
    Tags (if provided) are checked against known tags and added as a comma-separated metadata field.
    
    :param video_url: URL of the YouTube video.
    :param type: song, album_playlist, or playlist. album_playlist downloads a playlist as one file
    :param output_name: Base name for the output file. Defaults to video title.
    :param artist_name: Artist name to embed in metadata. Defaults to video uploader.
    :param tags: tags in a string.
    :return audio_file: The path to the downloaded audio file (FILE_TYPE) or None if error.
    :return error_str: None if no error, string containing error if error

    """

    type = type.lower()
    if type not in ["song", "album_playlist", "playlist"]:
        error_str = f'❗"{type}" is not a valid type. Valid types are either song, album_playlist, or playlist'
        print(error_str)
        return None,error_str
    
    # Get video info to set defaults if needed
    info = {}
    if not output_name or not artist_name:
        info,error_str = await get_video_info(video_url)
        if error_str != None:
            print(error_str)
            return None,error_str
    
    if not output_name:
        output_name = info.get("title", "Untitled")
    if not artist_name:
        artist_name = info.get("uploader", "Unknown")
    
    # Check against known lists. (authors and tags)
    artist_name = await check_and_update_artist(artist_name, interaction)
    if artist_name == False:  #user did not confirm addition of new author
        return None,"User did not confirm addition of new author"
    if tags:
        # Split the tags by commas and semicolons, and strip extra spaces
        tags_list = [tag.strip() for tag in re.split(r"[,;]", tags) if tag.strip()]
        
        # Process and update tags list
        tags_list = await check_and_update_tags(tags_list, interaction)
        if tags_list == False:  #user did not confirm addition of new tags
            return None,"User did not confirm addition of new tags"

        # Join them back into a properly formatted string
        #NOTE: need to change this if other file types are expected
        tags_str = "; ".join(tags_list)  #m4a uses semicolons
    else:
        tags_str = None

    # Construct the output file template; yt-dlp will append the proper extension.
    output_file_template = os.path.join(BASE_DIRECTORY, f"{output_name}.%(ext)s")
    
    # Build the metadata postprocessor args:
    meta_args = f"-metadata artist='{artist_name}'"
    if(type!="playlist"):
        meta_args += f" -metadata title='{output_name}'"

    if tags_str:
        meta_args += f" -metadata genre='{tags_str}'"
    if album or type=="playlist":
        meta_args += f" -metadata album='{album}'"
    
    #does the song already exist?
    if os.path.exists(os.path.join(BASE_DIRECTORY,f"{output_name}{FILE_EXTENSION}")):
        confirmation_str=f'"⚠️{output_name}{FILE_EXTENSION}" already exists, continue anyways?\nArguments: {meta_args}'
    else:
        confirmation_str=f'Arguments: {meta_args}'
    #confirm selection
    if (await ask_confirmation(interaction, confirmation_str)) == False:
        return None,"User did not confirm"

    #Update yt-dlp
    print("Updating yt-dlp...")
    update_command = f"{YT_DLP_PATH} -U"
    returncode, _, stderr = await run_command(update_command, True)
    
    if returncode != 0:
        error_str=f"Error updating yt-dlp: {stderr}"
        print(error_str)
        return None,error_str
    
    #if user doesn't want chapters, dont include flag. 
    if addtimestamps == False or type == "album_playlist":
        chapter_flag = "--no-embed-chapters"
    else:
        chapter_flag = "--embed-chapters"

    #Download video
    print("Download starting...")
    if(type=="song"):
        # Wrap the output file template in quotes to prevent shell misinterpretation of %(ext)s
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} --embed-thumbnail --add-metadata "
            f"{chapter_flag} --postprocessor-args \"{meta_args}\" -o \"{output_file_template}\" {video_url}"
        )
        print(f"Full command: {yt_dlp_cmd}")
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)

        if returncode == 0:
            print("Download complete.")
            return os.path.join(BASE_DIRECTORY, f"{output_name}{FILE_EXTENSION}"), None
        else:
            error_str = f"Error downloading: {stderr}"
            print(error_str)
            return None,error_str
    #need to add track metadata, remove title metadata, handle future calls of apply_timestamps
    elif type == "playlist":#download each song individually in a subfolder
        # Create directory
        dir = os.path.join(BASE_DIRECTORY, f"{output_name}")
        os.makedirs(dir, exist_ok=True)

        # Download individual tracks with metadata
        track_template = os.path.join(dir, f"%(title)s.{FILE_TYPE}")
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} --embed-thumbnail --add-metadata "
            f"--parse-metadata \"playlist_index:%(track_number)s\" "
            f"--no-embed-chapters --postprocessor-args \"{meta_args}\" "
            f"-o \"{track_template}\" {video_url}"
        )
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)
        
        if returncode != 0:
            error_str = f"Playlist download failed: {stderr}"
            print(error_str)
            return None, error_str

        if returncode != 0:
            # Truncate error message for Discord
            truncated_error = error[:1500] + "..." if len(error) > 1500 else error
            error_str = f"Combination failed: {truncated_error}"
            print(error_str)
            return None, error_str

        print("Playlist download complete")
        return dir, None
        
    elif type == "album_playlist":
        # Create temporary directory
        temp_dir = os.path.join(BASE_DIRECTORY, f"temp_{output_name}")
        os.makedirs(temp_dir, exist_ok=True)

        # Download individual tracks with metadata
        track_template = os.path.join(temp_dir, f"%(playlist_index)s_%(title)s.{FILE_TYPE}")
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} --embed-thumbnail --add-metadata "
            f"--no-embed-chapters --postprocessor-args \"{meta_args}\" "
            f"-o \"{track_template}\" {video_url}"
        )
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)
        
        if returncode != 0:
            error_str = f"Playlist download failed: {stderr}"
            print(error_str)
            return None, error_str

        # Collect and sort tracks
        track_files = sorted(
            [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith(FILE_EXTENSION)],
            key=lambda x: int(os.path.basename(x).split('_', 1)[0])
        )

        # Build chapters metadata
        chapters = []
        current_start = 0
        for track in track_files:
            # Get duration from file
            duration = await get_audio_duration(track)
            if not duration:
                duration = 0  # Fallback to 0 if duration can't be determined
            
            # Get title from filename
            title = os.path.basename(track).split('_', 1)[1].rsplit('.', 1)[0].replace("'", "\\'")
            
            chapters.append({
                'start': current_start,
                'end': current_start + duration,
                'title': title
            })
            current_start += duration

        # Generate FFmetadata
        metadata = [";FFMETADATA1"]
        for chapter in chapters:
            metadata.extend([
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={chapter['start']}",
                f"END={chapter['end']}",
                f"title={chapter['title']}"
            ])

        metadata_file = os.path.join(temp_dir, "chapters.txt")
        with open(metadata_file, 'w') as f:
            f.write('\n'.join(metadata))

        # Create concat list
        concat_file = os.path.join(temp_dir, "concat.list")
        with open(concat_file, 'w') as f:
            for track in track_files:
                f.write(f"file '{os.path.abspath(track)}'\n")

        # Combine tracks
        combined_file = os.path.join(BASE_DIRECTORY, f"{output_name}_combined{FILE_EXTENSION}")
        ffmpeg_cmd = (
            f"ffmpeg -f concat -safe 0 -i \"{concat_file}\" "
            f"-i \"{metadata_file}\" -map 0:a -map_chapters 1 "  # Explicitly map audio only
            f"-c copy \"{combined_file}\""
        )
        returncode, _, error = await run_command(ffmpeg_cmd, True)

        # Cleanup temp files
        shutil.rmtree(temp_dir)

        if returncode != 0:
            # Truncate error message for Discord
            truncated_error = error[:1500] + "..." if len(error) > 1500 else error
            error_str = f"Combination failed: {truncated_error}"
            print(error_str)
            return None, error_str

        # Apply thumbnail from first track or database
        first_track = track_files[0] if track_files else None
        if first_track:
            # Extract thumbnail from first track
            thumbnail_cmd = (
                f"ffmpeg -i \"{first_track}\" -map 0:v -c copy \"{temp_dir}/cover.jpg\""
            )
            await run_command(thumbnail_cmd)
            
            if os.path.exists(f"{temp_dir}/cover.jpg"):
                await apply_thumbnail_to_file(f"{temp_dir}/cover.jpg", combined_file)

        # Rename final file
        final_file = os.path.join(BASE_DIRECTORY, f"{output_name}{FILE_EXTENSION}")
        os.rename(combined_file, final_file)

        print("Album playlist download complete")
        return final_file, None