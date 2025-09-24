import os
import json
import difflib
import re
import shutil
from config.config_manager import config
from utils.core import run_command
from utils.discord_helpers import ask_confirmation
from utils.metadata import get_audio_duration,apply_thumbnail_to_file,get_audio_metadata,fetch_musicbrainz_data,replace_thumbnail
from mutagen import File
from mutagen.mp4 import MP4

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
                        album: str = None, addtimestamps: bool = None,usedatabase: bool=False, excludetracknumsforplaylist: bool = False) -> tuple:
    """
    Downloads a YouTube video as FILE_EXTENSION audio with embedded metadata.
    
    If output_name or artist_name is not provided, uses video title and uploader respectively.
    Tags (if provided) are checked against known tags and added as a comma-separated metadata field.
    
    :param video_url: URL of the YouTube video.
    :param type: song, album_playlist, or playlist. album_playlist downloads a playlist as one file
    :param output_name: Base name for the output file. Defaults to video title.
    :param artist_name: Artist name to embed in metadata. Defaults to video uploader.
    :param tags: tags in a string.
    :param album: album name. Must be supplied when type=playlist to get track numbers
    :param addtimestamps: if False, then chapters are not embedded
    :param usedatabase: for cover(s)
    :param excludetracknumsforplaylist: applies when type=playlist: if True: dont add track numbers. Default=False

    :return audio_file: The path to the downloaded "{audio file}{FILE_EXTENSION}" or None if error.
    :return error_str: None if no error, string containing error if error
    :return output_name: either same as pass in, or title from get_video_info()
    """

    type = type.lower()
    if type not in ["song", "album_playlist", "playlist"]:
        error_str = f'❗"{type}" is not a valid type. Valid types are either song, album_playlist, or playlist'
        print(error_str)
        return None, error_str, None

    # Get video info to set defaults if needed
    info = {}
    if not output_name or not artist_name:
        info,error_str = await get_video_info(video_url)
        if error_str != None:
            print(error_str)
            return None,error_str, None
    
    #usedatabase initialization
    embed_thumbnail = '--embed-thumbnail' if usedatabase is False else ''

    if not output_name:
        output_name = info.get("title", "Untitled")
    if not artist_name:
        artist_name = info.get("uploader", "Unknown")
    
    # Check against known lists. (authors and tags)
    artist_name = await check_and_update_artist(artist_name, interaction)
    if artist_name == False:  #user did not confirm addition of new author
        return None,"User did not confirm addition of new author", None
    if tags:
        # Split the tags by commas and semicolons, and strip extra spaces
        tags_list = [tag.strip() for tag in re.split(r"[,;]", tags) if tag.strip()]
        
        # Process and update tags list
        tags_list = await check_and_update_tags(tags_list, interaction)
        if tags_list == False:  #user did not confirm addition of new tags
            return None,"User did not confirm addition of new tags", None

        # Join them back into a properly formatted string
        #TODO: need to change this if other file types are expected
        tags_str = "; ".join(tags_list)  #m4a uses semicolons
    else:
        tags_str = None

    # Construct the output file template; yt-dlp will append the proper extension.
    output_file_template = os.path.join(BASE_DIRECTORY, f"{output_name}.%(ext)s")

    # Build the metadata postprocessor args for single/playlist mode:
    # NOTE: we will override title only for final combined file in album_playlist.
    meta_args = f"-metadata artist='{artist_name}'"
    if tags_str:
        meta_args += f" -metadata genre='{tags_str}'"
    if album:
        meta_args += f" -metadata album='{album}'"
    # For song or playlist (individual downloads), we include title override:
    #   song: title = output_name
    #   playlist: title override per-file is handled by yt-dlp --add-metadata (it embeds per-video metadata).
    # But for album_playlist, we do NOT override title for individual tracks.

    #does the song already exist?
    if os.path.exists(os.path.join(BASE_DIRECTORY, f"{output_name}{FILE_EXTENSION}")):
        confirmation_str = f'⚠️"{output_name}{FILE_EXTENSION}" already exists, continue anyways?\nArguments: {meta_args}'
    elif os.path.exists(os.path.join(BASE_DIRECTORY, f"{output_name}")):
        confirmation_str = f'⚠️"{output_name}" already exists, continue anyways?\nArguments: {meta_args}'
    else:
        confirmation_str = f'Arguments: {meta_args}'
    # confirm selection
    if (await ask_confirmation(interaction, confirmation_str)) == False:
        return None, "User did not confirm", None

    #Update yt-dlp
    print("Updating yt-dlp...")
    update_command = f"{YT_DLP_PATH} -U"
    returncode, _, stderr = await run_command(update_command, True)
    
    if returncode != 0:
        error_str = f"Error updating yt-dlp: {stderr}"
        print(error_str)
        return None, error_str, None

    # if user doesn't want chapters, don't include flag.
    if addtimestamps == False or type == "album_playlist":
        chapter_flag = "--no-embed-chapters"
    else:
        chapter_flag = "--embed-chapters"

    #Download video
    print("Download starting...")
    if type == "song":
        # Download single song, override title to output_name
        meta_args_song = meta_args + f" -metadata title='{output_name}'"
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} {embed_thumbnail} --add-metadata "
            f"{chapter_flag} --force-overwrites --postprocessor-args \"{meta_args_song}\" -o \"{output_file_template}\" {video_url}"
        )
        print(f"Full command: {yt_dlp_cmd}")
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)
        if returncode != 0:
            error_str = f"Error downloading: {stderr}"
            print(error_str)
            return None, error_str, None
        else:
            audio_file = os.path.join(BASE_DIRECTORY, f"{output_name}{FILE_EXTENSION}")
            print("Song Download complete.")
            return audio_file, None, output_name

    elif type == "playlist":
        # Download each track individually into subfolder; let yt-dlp embed per-video title via --add-metadata.
        subdir = os.path.join(BASE_DIRECTORY, f"{output_name}")
        os.makedirs(subdir, exist_ok=True)
        if excludetracknumsforplaylist:
            track_nums_arg=''
        else:
            track_nums_arg=f'--parse-metadata "playlist_index:%(track_number)s" '
        # Use meta_args + no title override, since yt-dlp's --add-metadata embeds each video’s title automatically.
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} {embed_thumbnail} --add-metadata "
            f"{track_nums_arg}"
            f"{chapter_flag} --force-overwrites --postprocessor-args \"{meta_args}\" "
            f"-o \"{os.path.join(subdir, '%(title)s.' + FILE_TYPE)}\" {video_url}"
        )
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)
        if returncode != 0:
            error_str = f"Playlist download failed: {stderr}"
            print(error_str)
            return None, error_str, None
        print("Playlist download complete")
        return subdir, None, output_name

    elif type == "album_playlist":
        # Download all tracks, then concatenate into one file with chapters
        # Key: do NOT override title per track here; let --add-metadata embed actual track title.
        # Later, for the combined file, we will override title to output_name.

        # 1. Create temporary directory
        temp_dir = os.path.join(BASE_DIRECTORY, f"temp_{output_name}")
        os.makedirs(temp_dir, exist_ok=True)

        # 2. Download individual tracks with metadata into temp_dir
        # No title override; use meta_args only (so yt-dlp --add-metadata embeds per-video metadata).
        track_template = os.path.join(temp_dir, f"%(playlist_index)s_%(title)s.{FILE_TYPE}")
        yt_dlp_cmd = (
            f"{YT_DLP_PATH} -x --audio-format {FILE_TYPE} --add-metadata "
            f"--no-embed-chapters --force-overwrites --postprocessor-args \"{meta_args}\" "
            f"-o \"{track_template}\" {video_url}"
        )
        returncode, _, stderr = await run_command(yt_dlp_cmd, True)
        if returncode != 0:
            error_str = f"Playlist download failed: {stderr}"
            print(error_str)
            return None, error_str, None

        # 3. Collect and sort track files by playlist index prefix
        track_files = sorted(
            [
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if f.endswith(FILE_EXTENSION)
            ],
            key=lambda x: int(os.path.basename(x).split('_', 1)[0])
        )

        # 4. Sanitize filenames: remove apostrophes from filenames so ffmpeg concat won't break.
        sanitized_track_files = []
        for track_path in track_files:
            dirname, basename = os.path.split(track_path)
            if "'" in basename:
                # New filename without apostrophes
                new_basename = basename.replace("'", "")
                new_path = os.path.join(dirname, new_basename)
                try:
                    os.replace(track_path, new_path)
                except Exception:
                    os.rename(track_path, new_path)
                sanitized_track_files.append(new_path)
            else:
                sanitized_track_files.append(track_path)
        # Use sanitized list for next steps
        track_files = sanitized_track_files

        # 5. (Optional) Get album name from first track metadata if not provided
        if not album and track_files:
            try:
                first_track = track_files[0]
                audio = MP4(first_track)
                if '\xa9alb' in audio.tags:
                    album = audio.tags['\xa9alb'][0]
                    # Update meta_args for final combined file
                    # (we'll apply in meta_args_combined below)
            except Exception as e:
                print(f"Error reading track metadata: {str(e)}")

        # 6. Build chapters metadata using embedded metadata titles (so apostrophes preserved in display)
        chapters = []
        current_start = 0
        for track in track_files:
            # Get duration from file in milliseconds
            duration = await get_audio_duration(track)
            if duration is None:
                duration = 0

            # Get the title from embedded metadata, falling back to filename if missing
            metadata = await get_audio_metadata(track)
            title_meta = metadata.get('title') or ""
            if title_meta:
                chapter_title = title_meta
            else:
                # Fallback: extract from filename after index_
                basename = os.path.basename(track)
                try:
                    title_part = basename.split('_', 1)[1]
                except IndexError:
                    title_part = os.path.splitext(basename)[0]
                chapter_title = os.path.splitext(title_part)[0]
            # Escape single quotes in chapter title for FFmetadata syntax:
            chapter_title_escaped = chapter_title.replace("'", r"\'")

            chapters.append({
                'start': current_start,
                'end': current_start + duration,
                'title': chapter_title_escaped
            })
            current_start += duration

        # Generate FFmetadata file
        metadata_lines = [";FFMETADATA1"]
        for chapter in chapters:
            metadata_lines.extend([
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={chapter['start']}",
                f"END={chapter['end']}",
                f"title={chapter['title']}"
            ])
        metadata_file = os.path.join(temp_dir, "chapters.txt")
        with open(metadata_file, 'w') as f:
            f.write('\n'.join(metadata_lines))

        # 7. Generate concat.list now that filenames have no apostrophes
        concat_file = os.path.join(temp_dir, "concat.list")
        with open(concat_file, 'w') as f:
            for track in track_files:
                abs_path = os.path.abspath(track)
                # Surround with single quotes so ffmpeg sees: file '/path/name.opus'
                f.write(f"file '{abs_path}'\n")

        # 8. Combine tracks with metadata for final file
        # Build meta_args for combined file: include artist, album (if any), and override title to output_name
        meta_args_combined = f"-metadata artist='{artist_name}'"
        if tags_str:
            meta_args_combined += f" -metadata genre='{tags_str}'"
        if album:
            meta_args_combined += f" -metadata album='{album}'"
        meta_args_combined += f" -metadata title='{output_name}'"

        combined_file = os.path.join(BASE_DIRECTORY, f"{output_name}_combined{FILE_EXTENSION}")
        ffmpeg_cmd = (
            f"ffmpeg -f concat -safe 0 -i \"{concat_file}\" "
            f"-i \"{metadata_file}\" -map_metadata 0 -map 0:a -map_chapters 1 "
            f"-c copy {meta_args_combined} \"{combined_file}\""
        )
        returncode, _, error = await run_command(ffmpeg_cmd, True)

        # 9. Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)

        if returncode != 0:
            error_str = f"Combination failed: {error}"
            print(error_str)
            return None, error_str, None

        # 10. Rename/move final file to desired name.ext
        final_file = os.path.join(BASE_DIRECTORY, f"{output_name}{FILE_EXTENSION}")
        try:
            os.replace(combined_file, final_file)
        except Exception:
            os.rename(combined_file, final_file)

        print("Album playlist download complete")
        return final_file, None, output_name

    else:
        return None, f"Invalid type provided: {type}", None