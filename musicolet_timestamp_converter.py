import subprocess
import json
import re
from utils import ask_confirmation, run_command
from config_manager import config

FILE_EXTENSION = config["download_settings"]["file_extension"]

async def apply_manual_timestamps_to_file(timestamps: str, audio_file: str):
    """Take a string of timestamps formatted as 'min:sec Chapter Title' per line and apply it to the file."""

    metadata = [";FFMETADATA1"]
    timebase = 1000  # FFmetadata timebase in milliseconds
    chapter_times = []

    # Parse timestamps
    for line in timestamps.strip().split("\n"):
        match = re.match(r"(\d+):(\d+)\s+(.+)", line.strip())
        if match:
            minutes, seconds, title = int(match[1]), int(match[2]), match[3]
            start_time = (minutes * 60 + seconds) * timebase  # Convert to milliseconds
            chapter_times.append((start_time, title))
        else:
            print(f"Skipping invalid format: {line}")

    # Ensure at least one chapter exists
    if not chapter_times:
        print("No valid timestamps found.")
        return

    # Assign END times correctly
    for i, (start_time, title) in enumerate(chapter_times):
        metadata.append("[CHAPTER]")
        metadata.append("TIMEBASE=1/1000")
        metadata.append(f"START={start_time}")

        # Set END to the start of the next chapter, or leave it open-ended for the last one
        if i < len(chapter_times) - 1:
            end_time = chapter_times[i + 1][0]
        else:
            end_time = ""  # Let FFmpeg decide the last chapter's duration

        metadata.append(f"END={end_time}")
        metadata.append(f"title={title}")

    # Write to metadata file
    metadata_file = "metadata.txt"
    with open(metadata_file, "w") as f:
        f.write("\n".join(metadata))

    # Apply metadata with FFmpeg
    ffmpeg_cmd = f'ffmpeg -i "{audio_file}" -i {metadata_file} -map_metadata 1 -codec copy -y "{audio_file}.tmp" && mv "{audio_file}.tmp" "{audio_file}"'
    await run_command(ffmpeg_cmd, True)

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
