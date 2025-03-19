import subprocess
import json
import re
from utils import ask_confirmation, run_command
from config_manager import config
from typing import Optional

FILE_EXTENSION = config["download_settings"]["file_extension"]

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


async def apply_manual_timestamps_to_file(timestamps: str, audio_file: str):
    """Convert timestamps to FFmetadata and apply them to an audio file."""
    
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
        print("No valid timestamps found.")
        return

    # Get total duration of audio file
    total_duration = await get_audio_duration(audio_file)
    if total_duration is None:
        return

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
    ffmpeg_cmd = f'ffmpeg -i "{audio_file}" -i {metadata_file} -map_chapters 1 -map_metadata 1 -c copy -y "{audio_file}.tmp" && mv "{audio_file}.tmp" "{audio_file}"'
    print(f"ffmpeg_cmd = {ffmpeg_cmd}")
    returncode, _, error = await run_command(ffmpeg_cmd, verbose=True)

    if returncode != 0:
        print(f"FFmpeg command failed: {error}")

    # Cleanup metadata file
    #try:
    #    import os
    #    os.remove(metadata_file)
    #except OSError as e:
    #    print(f"Warning: Failed to delete metadata file: {e}")

def format_timestamps_for_musicolet(chapters, chapter_file):
    """Converts json sorted timestamps into musicolet timestamps [mn:sc.ms]"""
    with open(chapter_file, "w") as f:
        for chapter in chapters:
            start_time = float(chapter["start_time"])
            minutes = int(start_time // 60)
            seconds = int(start_time % 60)
            milliseconds = int((start_time % 1) * 1000)
            chapter_name = chapter["tags"].get("title", "Unknown")
            f.write(f"[{minutes}:{seconds:02}.{milliseconds:03}]{chapter_name}\n")
    print(f"Chapters saved to {chapter_file}")
    return chapter_file        

async def extract_chapters(audio_file: str):
    """Extracts chapters from the audio file and saves them in a .txt file."""
    chapter_file = audio_file.replace(f"{FILE_EXTENSION}", ".txt")

    ffprobe_cmd = [
        "ffprobe", "-i", audio_file,
        "-print_format", "json", "-show_chapters", "-loglevel", "error"
    ]
    #################### use run_command() here
    print("Extracting chapter data...")
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        chapters = json.loads(result.stdout).get("chapters", [])
    except subprocess.CalledProcessError as e:
        print(f"Error: ffprobe failed with code {e.returncode}")
        return None

    if chapters:
        return format_timestamps_for_musicolet(chapters, chapter_file)
    else:
        print("No chapters found.")
        return None
