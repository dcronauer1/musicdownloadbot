import subprocess
import json
import os

# Parameters
yt_dlp_path = "/home/nas/nas/yt-dlp/yt-dlp"  # Absolute path to yt-dlp
base_directory = "/home/nas/nas/music"  # Directory where files will be downloaded
video_url = "https://www.youtube.com/watch?v=7cwrM12pOzU"
artist_name = "MyArtist"
output_name = "MyCustomName"

# Ensure base directory exists
os.makedirs(base_directory, exist_ok=True)

# Full paths for output
output_file = os.path.join(base_directory, f"{output_name}.m4a")
chapter_file = os.path.join(base_directory, f"{output_name}.txt")

# Download the video
yt_dlp_cmd = [
    yt_dlp_path, "-x", "--audio-format", "alac",
    "--embed-thumbnail", "--add-metadata", "--embed-chapters",
    "--postprocessor-args", f"-metadata artist='{artist_name}'",
    "-o", output_file, video_url
]

print("Downloading audio...")
try:
    subprocess.run(yt_dlp_cmd, check=True)
    print("Download complete.")
except subprocess.CalledProcessError as e:
    print(f"Error: yt-dlp failed with code {e.returncode}")
    exit(1)

# Extract chapter metadata
ffprobe_cmd = [
    "ffprobe", "-i", output_file,
    "-print_format", "json", "-show_chapters", "-loglevel", "error"
]

print("Extracting chapter data...")
try:
    result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
    chapters = json.loads(result.stdout).get("chapters", [])
except subprocess.CalledProcessError as e:
    print(f"Error: ffprobe failed with code {e.returncode}")
    exit(1)

# Generate chapter file
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
else:
    print("No chapters found.")

print("Process complete.")
