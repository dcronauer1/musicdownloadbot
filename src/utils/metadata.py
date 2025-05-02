import subprocess
import json
import os
from config.config_manager import config
import re
from typing import Optional
from utils.core import run_command
import sys
import asyncio
import musicbrainzngs
import requests
from mutagen import File
from mutagen.oggopus import OggOpus
from mutagen.flac import Picture
import base64
from utils.file_handling import find_file_case_insensitive

FILE_EXTENSION = config["download_settings"]["file_extension"]
DEFAULT_COVER_SIZE = config["download_settings"]["default_cover_size"]
BASE_DIRECTORY = config["download_settings"]["base_directory"]

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

async def fetch_musicbrainz_data(artist: str, title: str, release_type: str = None, size: str = DEFAULT_COVER_SIZE, strict: bool=True) -> tuple:
    """Fetch cover art binary data from MusicBrainz
    
    :param release_type: valid MusicBrainz release type (e.g., "album")
    :param size: cover size.
    :return: (image_data, error)
    """
    try:
        if(release_type):
            result = musicbrainzngs.search_releases(
                artist=artist,
                release=title,
                limit=5,
                type=release_type,
                strict=strict
            )
        else:
            result = musicbrainzngs.search_releases(
                artist=artist,
                release=title,
                limit=5,
                strict=strict
            )
        #NOTE: VALID_RELEASE_TYPES = ['nat', 'album', 'single', 'ep', 'broadcast', 'other', 'compilation', 'soundtrack', 'spokenword', 'interview', 'audiobook', 'live', 'remix', 'dj-mix', 'mixtape/street']
        #https://python-musicbrainzngs.readthedocs.io/en/latest/api/#musicbrainzngs.musicbrainz.VALID_RELEASE_TYPES
                
        if not result.get('release-list'):
            return None, "No matching releases found"

        # Find first release with cover art
        for release in result['release-list']:
            mbid = release['id']
            try:
                # Get list of images for this release
                image_list = musicbrainzngs.get_image_list(mbid)
                
                for image in image_list.get('images', []):
                    if image.get('front', False):
                        # Fetch actual image binary data
                        image_data = musicbrainzngs.get_image(mbid, image['id'], size)
                        
                        # Convert to bytes if needed (API typically returns bytes directly)
                        if isinstance(image_data, str):
                            image_data = image_data.encode()
                            
                        return image_data, None
                        
            except musicbrainzngs.WebServiceError as e:
                print(f"Error fetching images for {mbid}: {str(e)}")
                continue

        return None, "No valid artwork found"

    except musicbrainzngs.WebServiceError as e:
        return None, f"MusicBrainz API Error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

async def apply_thumbnail_to_file(thumbnail_input: str | bytes, audio_file: str):
    """Apply a thumbnail to a file using either binary data or a URL."""
    temp_file = "temp_cover.png"
    
    try:
        # Handle different input types
        if isinstance(thumbnail_input, bytes):
            # Write binary data directly to temp file
            with open(temp_file, "wb") as f:
                f.write(thumbnail_input)
            print(f"Temp thumbnail downloaded using binary image data for: {audio_file}")
        else:
            # Assume it's a URL and download
            print(f"⚠️Downloading thumbnail from URL: {thumbnail_input}")
            returncode, _, error = await run_command(f'wget -O "{temp_file}" "{thumbnail_input}"')
            if returncode != 0:
                return f"❌Download failed: {error}"

        # Common processing for both input types
        if audio_file.endswith('.opus'):
            # OPUS handling with mutagen
            with open(temp_file, "rb") as f:
                image_data = f.read()

            # Create FLAC-style picture metadata
            pic = Picture()
            pic.data = image_data
            pic.type = 3    # Cover (front)
            pic.mime = "image/png" if image_data.startswith(b'\x89PNG') else "image/jpeg"
            pic.desc = "Cover art"
            
            audio = OggOpus(audio_file)
            audio["METADATA_BLOCK_PICTURE"] = [base64.b64encode(pic.write()).decode()]
            audio.save()
            print(f"✅Thumbnail updated (OPUS): {audio_file}")
            return True

        else:
            # FFmpeg handling for other formats
            ffmpeg_cmd = (
                f'ffmpeg -y -i "{audio_file}" -i "{temp_file}" '
                f'-map 0 -map 1 -c copy -disposition:v attached_pic "temp{FILE_EXTENSION}"'
            )
            returncode, _, error = await run_command(ffmpeg_cmd, True)
            
            if returncode == 0:
                await run_command(f'mv "temp{FILE_EXTENSION}" "{audio_file}"')
                print(f"✅Thumbnail updated (FFmpeg): {audio_file}")
                return True
            return f"❌FFmpeg failed: {error}"

    except Exception as e:
        return f"❌apply_thumbnail_to_file() Error: {str(e)}"
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

#replace_thumbnail(title,playlist=True,cover_URL=None, strict=True, releasetype = None, artist_name, album=None, size=None)
async def replace_thumbnail(title: str,playlist:bool=False, cover_URL:str=None, strict:bool=True, releasetype: str = None,
        artist:str=None, album:str=None, size: str = DEFAULT_COVER_SIZE) -> tuple: 
    """
    Helper function to apply thumbnails to a video, or an entire playlist
    :param title: title of song or playlist (subdirectory songs are stored under)
    :param playlist: True when using a playlist (ie subdir with songs). Default False.
    
    :param cover_URL: if None, then use database
    :param strict: default True. strict database querying
    :param releasetype: NOTE check replace_thumbnail_command() in main.py. change this comment when that is finished
    :param artist: manual fill for usedatabase (ignore unless needed)
    :param album: Use if thumbnail can't be found with strict & title. NOTE: will search metadata if None
    
    :param size: Cover size. Valid values are 250, 500, or 1200. Other values default to largest size (not recommended)

    :return: Tuple: output str, err str. if output None then error. 
            NOTE: can still return error str on success (failed database lookup) 
            NOTE: if sending outputs to user, use safe_send()!
    """
    #default some of the params here (so if None is passed in then do default)
    if size==None:
        size=DEFAULT_COVER_SIZE
    #etc
    #NOTE todo above
    
    subdir = os.path.join(BASE_DIRECTORY, f"{title}")
    if playlist:
        subdir_list = os.listdir(subdir)    #get list of files in subdir       
    else:
        audio_file = find_file_case_insensitive(BASE_DIRECTORY, f"{title}{FILE_EXTENSION}")
        subdir_list=[audio_file] #this is the single track in list form
    
    success_list = []
    thumbnail_error = "" #dont stop execution on database errors, collect and continue
    for audio_file in subdir_list:
        #add extensions to each file if playlist
        if audio_file.endswith(FILE_EXTENSION) and playlist:
            title = audio_file
            title = os.path.splitext(title)[0]
            audio_file = os.path.join(subdir, audio_file)   #get full path of each playlist entry

        if cover_URL == None: #cover_URL == None: (use database)
            metadata = await get_audio_metadata(audio_file)
            if artist == None:
                artist = metadata.get('artist', None)
            if artist == None:
                thumbnail_error += f"⚠️Unknown artist for __{title}__, please supply one manually"
                print(f"⚠️Unknown artist for {title}, please supply one manually")
                continue    #keep checking other files, return this error later
            if album == None:
                album = metadata.get('album',None)
            
            #NOTE
            #add album fallback here
            #wait maybe only check album once and store that? then if below fails just set image_data to the stored image?
            #would have an issue if playlist has different albums but idc
            #check notes for bad temp code


            image_data, error = await fetch_musicbrainz_data(artist, title, releasetype, size, strict)
            if error:
                thumbnail_error += f"❌Database lookup failed for __{title}__: {error[:40]}\n" #truncate error
                print(f"❌Database lookup failed for {title}:\n{error}")
                continue    #keep checking other files, return this error later
            if not image_data:
                thumbnail_error += f"❌No artwork found for __{title}__\n"
                print(f"❌No artwork found for {title}")
                continue    #keep checking other files, return this error later
            
            result = await apply_thumbnail_to_file(image_data, audio_file)
            if result is True:
                success_list.append(f"- {title}")
            else:
                thumbnail_error += f"❗Error applying thumbnail for __{title}__: {result[:40]}" #truncate error
                print(f"❗Error applying thumbnail for {title}:\n{result}")
        else: #cover_URL != None: (DONT use database)
            result = await apply_thumbnail_to_file(cover_URL, audio_file)
            if (result == True):
                success_list.append(f"{title}")
            else:   
                thumbnail_error += f"❗Error applying thumbnail for __{title}__: {result[:40]}" #truncate error
                print(f"❗Error applying thumbnail for {title}:\n{result}")
    output = None
    error_str = None
    if(success_list != []):
        success_string = "\n".join(success_list)
        output = f"🎊Thumbnail(s) for:\n{success_string}\nupdated from MusicBrainz!"
    if(thumbnail_error != ""):
        error_str=f"❗Error(s): check console for more detail:\n{thumbnail_error}"
    return output,error_str

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