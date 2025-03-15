import subprocess
import json
import os

def extract_chapters(audio_file: str):
    """Extracts chapters from the audio file and saves them in a .txt file."""
    chapter_file = audio_file.replace(".m4a", ".txt")

    ffprobe_cmd = [
        "ffprobe", "-i", audio_file,
        "-print_format", "json", "-show_chapters", "-loglevel", "error"
    ]

    print("Extracting chapter data...")
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        chapters = json.loads(result.stdout).get("chapters", [])
    except subprocess.CalledProcessError as e:
        print(f"Error: ffprobe failed with code {e.returncode}")
        return None

    if chapters:
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
    else:
        print("No chapters found.")
        return None
