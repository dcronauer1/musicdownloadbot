import subprocess
import json

# Parameters
video_url = "https://www.youtube.com/watch?v=7cwrM12pOzU"
artist_name = "MyArtist"
output_name = "MyCustomName"

# Download the video
yt_dlp_cmd = [
    "yt-dlp", "-x", "--audio-format", "alac",
    "--embed-thumbnail", "--add-metadata", "--embed-chapters",
    "--postprocessor-args", f"-metadata artist='{artist_name}'",
    "-o", f"{output_name}.m4a", video_url
]

subprocess.run(yt_dlp_cmd, check=True)

# Extract chapter metadata
ffprobe_cmd = [
    "ffprobe", "-i", f"{output_name}.m4a",
    "-print_format", "json", "-show_chapters", "-loglevel", "error"
]

result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
chapters = json.loads(result.stdout).get("chapters", [])

# Generate chapter file
with open(f"{output_name}_chapters.txt", "w") as f:
    for chapter in chapters:
        start_time = float(chapter["start_time"])
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        milliseconds = int((start_time % 1) * 1000)
        chapter_name = chapter["tags"].get("title", "Unknown")
        f.write(f"[{minutes}:{seconds:02}.{milliseconds:03}]{chapter_name}\n")

print(f"Download complete. Chapters saved to {output_name}_chapters.txt")
