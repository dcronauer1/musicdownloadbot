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
MUSIC_DIRECTORY = config["download_settings"]["music_directory"]
TEMP_DIRECTORY = config["directory_settings"]["temp_directory"]

try:
    musicbrainzngs.set_useragent(
        app=config["musicbrainz"]["app_name"],
        version="1.0",
        contact=config["musicbrainz"]["contact_email"]
    )
    musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
except KeyError as e:
    print(f"❌ MusicBrainz configuration missing: {str(e)}")
    print("Add these to your config.json under 'bot_settings':")
    print("- app_name\n- contact_email")
    sys.exit(1)

async def fetch_musicbrainz_data(artist: str, title: str, release_type: str = None, 
                                 size: str = DEFAULT_COVER_SIZE, strict: bool = True) -> tuple:
    """Fetch cover art with improved reliability and direct Cover Art Archive access"""
    try:
        # Try release groups first with direct CAA access
        rg_result = musicbrainzngs.search_release_groups(
            artist=artist,
            releasegroup=title,
            limit=5,
            strict=strict
        )
        
        for rg in rg_result.get('release-group-list', []):
            rg_id = rg['id']
            try:
                # Direct Cover Art Archive access
                cover_data = await fetch_from_coverartarchive(rg_id, size, "release-group")
                return cover_data, None
            except Exception as e:
                print(f"RG Direct CAA failed {rg_id}: {str(e)}")

        # Then try individual releases with direct CAA access
        search_params = {"artist": artist, "release": title, "limit": 10, "strict": strict}
        if release_type:
            search_params["type"] = release_type
            
        result = musicbrainzngs.search_releases(**search_params)
        
        for release in result.get('release-list', []):
            mbid = release['id']
            try:
                # Direct Cover Art Archive access
                cover_data = await fetch_from_coverartarchive(mbid, size, "release")
                return cover_data, None
            except Exception as e:
                print(f"Release Direct CAA failed {mbid}: {str(e)}")

        return None, "No artwork found via direct methods"

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

async def fetch_from_coverartarchive(mbid: str, size: str, entity_type: str) -> bytes:
    """Directly fetch cover art from Cover Art Archive"""
    # Size mapping - Cover Art Archive supports these sizes
    size_map = {
        "250": "250",
        "500": "500",
        "1200": "1200",
        "large": "1200"
    }
    size_str = size_map.get(size, "1200")  # Default to large
    
    # First try with specific size
    url = f"https://coverartarchive.org/{entity_type}/{mbid}/front-{size_str}.jpg"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        return response.content
    
    # Then try without size parameter
    print("Trying without size parameter")
    url = f"https://coverartarchive.org/{entity_type}/{mbid}/front.jpg"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        return response.content
    
    # Try with different size if original failed
    if size_str != "1200":
        print("Trying size 1200 parameter")
        url = f"https://coverartarchive.org/{entity_type}/{mbid}/front-1200.jpg"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content
    
    raise Exception(f"Cover Art Archive error: HTTP {response.status_code}")

async def apply_thumbnail_to_file(thumbnail_input: str | bytes, audio_file: str, isFile: bool = False):
    """Apply a thumbnail to a file using either binary data or a URL.\n
    :param thumbnail_input: either URL, raw binary data, or (if isFile==True) the full file path.
    :param isFile: skip writing image file, use thumbnail_input as the file
    :return result: True on success, else error string"""    
    try:
        if isFile:
            if os.path.exists(thumbnail_input):
                temp_file = thumbnail_input
            else:
                return "isFile==True but thumbnail_input file does not exist"
        else:
            title = os.path.basename(audio_file)
            temp_file = os.path.join(TEMP_DIRECTORY,f"{title}_cover.png")
            # Handle different input types
            if isinstance(thumbnail_input, bytes): #binary data
                # Write binary data directly to temp file
                with open(temp_file, "wb") as f:
                    f.write(thumbnail_input)
                print(f"Temp thumbnail downloaded using binary image data for: {audio_file}")
            else: #URL
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
        if not isFile:
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
    metadata_file = os.path.join(TEMP_DIRECTORY,"metadata.txt")
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

#replace_thumbnail(title,playlist=True,cover_URL=None, album=None, artist=None, strict=True, releasetype = None, size=None)
async def replace_thumbnail(title: str=None, playlist:bool=False, cover_URL:str=None, album:str=None, artist:str=None,
        strict:bool=True, releasetype: str = None, size: str = DEFAULT_COVER_SIZE) -> tuple: 
    """
    Function to apply thumbnails to a music/video file, or an entire playlist\n
    Either title, album, or both must be provided:
    * Use title if working with a single, or a playlist where you don't want a fallback cover
    * Use album if working with an album, and you would like a fallback cover.
    * Use both if title != album. title will be used for the name of the folder/file, while album will be used to find an album cover

    :param title: Title of song or playlist (subdirectory songs are stored under).
        Can set to None and use album instead
    :param playlist: True when using a playlist (ie subdir with songs). Default False.
    
    :param cover_URL: if None, then use database

    :param album: Used if thumbnail can't be found with title, or if title is None.
    :param artist: Use if not in metadata
    :param strict: default True. strict database querying
    :param releasetype: TODO check replace_thumbnail_command() in main.py. change this comment when that is finished
    
    :param size: Cover size. Valid values are 250, 500, or 1200. Other values default to largest size (not recommended)

    :return: Tuple: output str, err str. if output None then error. 
            NOTE: can still return error str on success (failed database lookup) 
            NOTE: if sending outputs to user, use safe_send()!
    """
    success_list = []
    thumbnail_error = "" #dont stop execution on database errors, collect and continue
    album_cover_found_str = "not "
    async def _fetch_data(_artist,_title,_releasetype):
        """Nested function to run fetch_musicbrainz_data() and handle errors

        :return _image_data: None on error"""
        nonlocal thumbnail_error
        _image_data, error = await fetch_musicbrainz_data(_artist, _title, _releasetype, size, strict)
        if error:
            #database error truncated
            thumbnail_error += f"⚠️DB lookup failed for __{_title}__: {error[:80]}\n"
            print(f"⚠️DB lookup failed for {_title}:\n{error}")
            return None    #keep checking other files, return this error later
        if not _image_data:
            temp_error = f"❌No artwork found for {_title}"
            thumbnail_error += temp_error+"\n"
            print(temp_error)
            return None    #keep checking other files, return this error later
        return _image_data
    async def _apply_thumbnail(_image,_audio_file,_title):
        """Nested function to run apply_thumbnail_to_file() and handle errors\n
        :param _image: either image_data or cover_URL
        :param _audio_file: full path of audio file
        :return result: True on success, else error"""
        nonlocal thumbnail_error

        result = await apply_thumbnail_to_file(_image, _audio_file)
        if result == True:
            success_list.append(f"- {_title}")
        else:#error
            thumbnail_error += f"❗Error applying thumbnail for __{_title}__:\n- {result[:40]}\n" #truncate error
            print(f"❗Error applying thumbnail for {_title}:\n{result}")
        return result
    
    #default some of the params here (so if None is passed in then do default)
    if title == None or title == "":
        if album == None or album == "":
            return None, "replace_thumbnail(): Title and album can't both be None. At least one must be provided."
        title = album   #use album as title
    if size==None:
        size=DEFAULT_COVER_SIZE
    #etc
    #TODO above
    
    subdir = os.path.join(MUSIC_DIRECTORY, f"{title}")
    if playlist:
        #get list of files in subdir (only file.ext, not full path)
        subdir_list = [f for f in os.listdir(subdir) if not f.endswith('.txt')] 
    else:
        audio_file = find_file_case_insensitive(MUSIC_DIRECTORY, f"{title}{FILE_EXTENSION}")
        subdir_list=[audio_file] #this is the single track's *full directory* in list form

    if subdir_list == [] or subdir_list == None:
        error_str = "❗File/Playlist does not exist"
        print(error_str)
        return None, error_str
        
    if album:
        #get metadata from first track 
        if playlist:
            audio_file_temp = os.path.join(subdir, subdir_list[0])
            metadata = await get_audio_metadata(audio_file_temp)
        else:
            metadata = await get_audio_metadata(subdir_list[0])

        if artist:
            album_artist = artist
        else:
            #get artist from metadata
            album_artist = metadata.get('artist', None)

        print(f"Searching for album cover")
        image_data_album = await _fetch_data(album_artist, album,"album")
        if image_data_album == None:
            #get album title from metadata and try again
            print("Trying metadata album title:")
            album_metadata = metadata.get('album', None)
            image_data_album = await _fetch_data(album_artist, album_metadata,"album")
            if image_data_album == None:
                temp_error = f"⚠️No album cover found"
                thumbnail_error += temp_error+"\n"
                print(temp_error)
        if image_data_album:
            album_cover_found_str = ""
            print("Album cover found")
            if releasetype == None and playlist == False: 
                #since using album, use album release type if one wasnt provided, so the album cover is used instead of one from title.
                releasetype = "album"   
    else:
        image_data_album = None
        print(f"Album not provided")

    #TODO: make each iteration async
    for audio_file in subdir_list:
        print(f"\nStarting download for {audio_file}")
        #add extensions to each file if playlist
        if audio_file.endswith(FILE_EXTENSION) and playlist:
            title = audio_file
            title = os.path.splitext(title)[0]
            audio_file = os.path.join(subdir, audio_file)   #get full path of each playlist entry
        #title is already title for singles
        if cover_URL == None: #use database
            #if its an album and releasetype is album, then just use the already gotten album cover
            if album and releasetype == "album": #album provided and releasetype is album, so only use album cover (even if None)
                image_data = image_data_album
            else:
                metadata = await get_audio_metadata(audio_file)

                if artist:
                    metadata_artist = artist
                else:
                    metadata_artist = metadata.get('artist', None)
                
                if metadata_artist == None:  #check if there is an artist, throw warn if not
                    temp_error = f"⚠️Unknown artist for __{title}__, please supply one manually"
                    thumbnail_error += temp_error+"\n"
                    print(temp_error)
                
                metadata_title = metadata.get('title', None)
                #get cover:
                image_data = await _fetch_data(metadata_artist,metadata_title,releasetype)
                if image_data == None and title != metadata_title:
                    #not same, try file title instead
                    print("Trying file title:")
                    image_data = await _fetch_data(metadata_artist,title,releasetype)

            if image_data == None:
                if image_data_album:    #album cover was found, so use that as fallback
                    await _apply_thumbnail(image_data_album,audio_file,title)
                else:
                    continue    #no image data, continue with other tracks
            else:
                await _apply_thumbnail(image_data,audio_file,title)
        else: #cover_URL != None: (DONT use database)
            await _apply_thumbnail(cover_URL,audio_file,title)

    output = None
    error_str = None
    if(success_list != []): #updated in _apply_thumbnail
        success_string = "\n".join(success_list)
        output = f"🎊Thumbnails for:\n{success_string}\nupdated from MusicBrainz!"
    if(thumbnail_error != ""):
        error_str=f"Album cover was {album_cover_found_str}found:\n❗Error(s): check console for more detail:\n{thumbnail_error}"
    return output,error_str