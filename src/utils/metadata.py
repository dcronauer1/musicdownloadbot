import subprocess
import json
import os
from config.config_manager import config
import re
from typing import Optional
from utils.core import run_command
import sys

import musicbrainzngs
import requests
from mutagen import File
from mutagen.oggopus import OggOpus
from mutagen.flac import Picture
import base64

FILE_EXTENSION = config["download_settings"]["file_extension"]     


try:
    musicbrainzngs.set_useragent(
        app=config["musicbrainz"]["app_name"],
        version="1.0",
        contact=config["musicbrainz"]["contact_email"]
    )
except KeyError as e:
    print(f"❌ MusicBrainz configuration missing: {str(e)}")
    print("Add these to your config.json under 'bot_settings':")
    print("- app_name\n- contact_email")
    sys.exit(1)

async def get_audio_metadata(audio_file: str) -> dict:
    """Get metadata from audio file using mutagen"""
    try:
        if audio_file.lower().endswith('.opus'):
            # Handle OPUS files specifically
            f = OggOpus(audio_file)
            return {
                'artist': f.get('artist', [None])[0],
                'album': f.get('album', [None])[0],
                'title': f.get('title', [None])[0],
                'date': f.get('date', [None])[0],
                'genre': f.get('genre', [None])[0]
            }
        else:
            # Handle other file types (m4a, mp3, etc)
            f = File(audio_file)
            return {
                'artist': f.get('\xa9ART', [None])[0],
                'album': f.get('\xa9alb', [None])[0],
                'title': f.get('\xa9nam', [None])[0],
                'date': f.get('\xa9day', [None])[0],
                'genre': f.get('\xa9gen', [None])[0]
            }
    except Exception as e:
        print(f"Metadata read error: {str(e)}")
        return {
            'artist': None,
            'album': None,
            'title': None,
            'date': None,
            'genre': None
        }

async def fetch_musicbrainz_data(artist: str, title: str, release_type: str = None) -> tuple:
    """Fetch cover art URL from MusicBrainz with proper URL construction
    
    :param release_type: valid MusicBrainz release type (e.g., "album")
    """
    try:
        result = musicbrainzngs.search_releases(
            artist=artist,
            release=title,
            limit=5,
            strict=False,
            type=release_type  # Add release_type parameter
        )
        
        if not result.get('release-list'):
            return None, None, "No matching releases found"

        # Find first release with cover art
        for release in result['release-list']:
            mbid = release['id']
            try:
                # Get cover art information
                coverart = musicbrainzngs.get_image_list(mbid)
                for image in coverart.get('images', []):
                    if image.get('front', False):
                        # Construct proper URL
                        return f"https://coverartarchive.org/release/{mbid}/{image['id']}.jpg", None, None
            except musicbrainzngs.WebServiceError:
                continue

        return None, None, "No valid artwork URL found"

    except musicbrainzngs.WebServiceError as e:
        return None, None, f"MusicBrainz API Error: {str(e)}"
    except Exception as e:
        return None, None, f"Unexpected error: {str(e)}"

async def get_audio_duration(audio_file: str) -> Optional[int]:
    """Get the duration of the audio file in milliseconds using ffprobe."""
    cmd = f'ffprobe -i "{audio_file}" -show_entries format=duration -v quiet -of csv="p=0"'
    returncode, duration_str, error = await run_command(cmd)

    if returncode != 0 or not duration_str.strip():
        print(f"Error getting duration for {audio_file}: {error or 'Empty duration output'}")
        return None

    try:
        return int(float(duration_str.strip()) * 1000)  # Convert seconds to milliseconds
    except ValueError:
        print(f"Failed to parse audio duration: {duration_str}")
        return None

async def apply_thumbnail_to_file(thumbnail_url: str, audio_file: str):
    """Apply a thumbnail to a file using FFMPEG or mutagen for Opus files."""
    print(f"⚠️thumbnail_url: {thumbnail_url}")
    temp_file = "temp_cover.png"
    
    # Download the thumbnail
    returncode, _, error = await run_command(f'wget -O "{temp_file}" "{thumbnail_url}"')
    if returncode != 0:
        try: os.remove(temp_file)
        except: pass
        return f"❌Thumbnail download failed: {error}"

    try:
        if audio_file.endswith('.opus'):
            # Read image data
            with open(temp_file, "rb") as f:
                image_data = f.read()

            # Create FLAC-style picture metadata
            pic = Picture()
            pic.data = image_data
            pic.type = 3  # Cover (front)
            pic.mime = "image/png"
            pic.desc = "Cover art"
            pic_data = base64.b64encode(pic.write()).decode()

            # Embed in OPUS file
            audio = OggOpus(audio_file)
            audio["METADATA_BLOCK_PICTURE"] = [pic_data]
            audio.save()
            print("✅ Thumbnail updated (mutagen)")
            return True

        else:
            # FFMPEG handling for m4a and others
            ffmpeg_cmd = (
                f'ffmpeg -y -i "{audio_file}" -i "{temp_file}" '
                f'-map 0 -map 1 -c copy -disposition:v attached_pic "temp{FILE_EXTENSION}"'
            )
            returncode, _, error = await run_command(ffmpeg_cmd, True)
            
            if returncode == 0:
                await run_command(f'mv "temp{FILE_EXTENSION}" "{audio_file}"')
                print("✅ Thumbnail updated (ffmpeg)")
                return True
            return f"❌ FFmpeg failed: {error}"

    except Exception as e:
        return f"❌ Error: {str(e)}"
        
    finally:
        try: os.remove(temp_file)
        except: pass

async def apply_timestamps_to_file(timestamps: str, audio_file: str, canRemove: bool = False) ->tuple:
    """Convert timestamps to FFmetadata and apply them to an audio file.
    
    :param timestamps: expected to be in the format of [min:sec]"title"
    :param canRemove: if True, then timestamps can be wiped from the file.
    
    :return: bool for success/fail, err
    """
    
    if timestamps==None and canRemove:
        # Special case: Remove existing chapters
        ffmpeg_cmd = (
            f'ffmpeg -i "{audio_file}" '
            f'-map_metadata 0 '  # Preserve existing metadata
            f'-map_chapters -1 '  # Remove all chapters
            f'-c copy -y "{audio_file}.tmp.{FILE_EXTENSION}" '
            f'&& mv "{audio_file}.tmp.{FILE_EXTENSION}" "{audio_file}"'
        )
        print(f"Removal command: {ffmpeg_cmd}")
        returncode, _, error = await run_command(ffmpeg_cmd, verbose=True)
        
        if returncode != 0:
            error = f"Chapter removal failed:\n{error}"
            print(error)
            return False, error
        return True, None
    
    #not removing timestamps:
    metadata = [";FFMETADATA1"]
    timebase = 1000  # FFmetadata timebase in milliseconds
    chapter_times = []

    # Improved regex to support optional milliseconds
    timestamp_pattern = re.compile(r"(\d+):(\d+)(?:\.(\d+))?\s+(.+)")  

    # Parse timestamps
    for line in timestamps.strip().split("\n"):
        match = timestamp_pattern.match(line.strip())
        if match:
            minutes, seconds, millis, title = int(match[1]), int(match[2]), match[3], match[4].strip()
            millis = int(millis) if millis else 0
            start_time = (minutes * 60 + seconds) * timebase + millis  # Convert to milliseconds
            chapter_times.append((start_time, title))
        else:
            print(f"Skipping invalid format: {line}")

    # Ensure at least one chapter exists
    if not chapter_times:
        error = "No valid timestamps found."
        print(error)
        return False, error

    # Get total duration of audio file
    total_duration = await get_audio_duration(audio_file)
    if total_duration is None:
        error = "Return Duration is None"
        print(error)
        return False, error

    # Assign END times correctly
    for i, (start_time, title) in enumerate(chapter_times):
        metadata.append("[CHAPTER]")
        metadata.append("TIMEBASE=1/1000")
        metadata.append(f"START={start_time}")

        # Set END to the start of the next chapter or the total duration for the last one
        end_time = chapter_times[i + 1][0] if i < len(chapter_times) - 1 else total_duration
        metadata.append(f"END={end_time}")
        metadata.append(f"title={title.replace('\"', '\'')}")  # Escape quotes in titles

    # Write metadata to file
    metadata_file = "metadata.txt"
    with open(metadata_file, "w") as f:
        f.write("\n".join(metadata))

    # Apply metadata with FFmpeg
    ffmpeg_cmd = (
        f'ffmpeg -i "{audio_file}" -i {metadata_file} '
        f'-map_metadata 0 -map_chapters 1 '
        f'-c copy -y "{audio_file}.tmp.{FILE_EXTENSION}" '
        f'&& mv "{audio_file}.tmp.{FILE_EXTENSION}" "{audio_file}"'
    )
    print(f"ffmpeg_cmd = {ffmpeg_cmd}")
    returncode, _, error = await run_command(ffmpeg_cmd, verbose=True)

    # Cleanup metadata and temp.{FILE_EXTENSION} file
    try:
        os.remove(metadata_file)
    except OSError as e:
        print(f"Warning: Failed to delete temp metadata file: {e}")

    if returncode != 0:
        error = f"FFmpeg command failed:\n{error}"
        print(error)
        return False, error
    return True, None

async def extract_chapters(audio_file: str) -> tuple:
    """Extracts chapters from the audio file and saves them in a .txt file in the format musicolet uses.

    :return: chapter_file,err    
    """
    chapter_file = audio_file.replace(f"{FILE_EXTENSION}", ".txt")

    ffprobe_cmd = f'ffprobe -i "{audio_file}" -print_format json -show_chapters -loglevel error'

    print("Extracting chapter data...")
    returncode, output, error = await run_command(ffprobe_cmd,verbose=True)
     
    if returncode != 0:
        error_msg = f"FFprobe error ({returncode}):\n{error}"
        print(error_msg)
        return None, error_msg

    try:
        chapters = json.loads(output).get("chapters", [])
    except json.JSONDecodeError:
        error_msg = "Failed to parse FFprobe output"
        print(error_msg)
        return None, error_msg
    #if chapters exist, then make file, else return nothing
    if chapters:
        return format_timestamps_for_musicolet(chapters, chapter_file)
    else:
        error_str = "No chapters found."
        print(error_str)
        return None,error_str

def format_timestamps_for_musicolet(chapters, chapter_file) -> tuple:
    """Converts json sorted timestamps into musicolet timestamps [mn:sc.ms]"""
    try:
        with open(chapter_file, "w") as f:
            for chapter in chapters:
                start_time = float(chapter["start_time"])
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                milliseconds = int((start_time % 1) * 1000)
                chapter_name = chapter["tags"].get("title", "Unknown")
                f.write(f"[{minutes}:{seconds:02}.{milliseconds:03}]{chapter_name}\n")
        print(f"Chapters saved to {chapter_file}")
        return chapter_file, None 
    except Exception as e:
        error_msg = f"Error formatting chapters: {str(e)}"
        print(error_msg)
        return None, error_msg