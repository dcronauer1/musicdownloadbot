import subprocess
import json
import re
from utils import ask_confirmation, run_command

async def apply_manual_timestamps_to_file(timestamps: str, audio_file: str):
    """take a string of timestamps formatted as "min:sc 'chapter title'\n", and apply it to the file"""
    #convert
    metadata = [";FFMETADATA1"]
    timebase = 1000  # FFmetadata timebase in milliseconds
    start_time = 0  # Initial chapter start time

    # Split into lines and process each one
    for line in timestamps.strip().split("\n"):
        match = re.match(r"(\d+):(\d+)\s+(.+)", line)
        if match:
            minutes, seconds, title = int(match[1]), int(match[2]), match[3]
            end_time = (minutes * 60 + seconds) * timebase  # Convert to milliseconds

            # Append chapter metadata
            metadata.append("[CHAPTER]")
            metadata.append("TIMEBASE=1/1000")
            metadata.append(f"START={start_time}")
            metadata.append(f"END={end_time}")
            metadata.append(f"title={title}")

            # Update start_time for the next chapter
            start_time = end_time
        else:
            print(f"Skipping invalid format: {line}")
    converted_chapters = "\n".join(metadata)

    ffmpeg_covert_cmd = (f"ffmpeg -i \"{audio_file}\" -i {converted_chapters} -map_metadata 1 -codec copy output_video.mp4")
    #need to make sure above replaces existing
    run_command(ffmpeg_covert_cmd, True)

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

async def extract_chapters(interaction, audio_file: str):
    """Extracts chapters from the audio file and saves them in a .txt file."""
    chapter_file = audio_file.replace(".m4a", ".txt")

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
        format_timestamps_for_musicolet(chapters, chapter_file)
    else:
        print("No chapters found.")
        return None
