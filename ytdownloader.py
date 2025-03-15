import subprocess
import os
from config_manager import YT_DLP_PATH, BASE_DIRECTORY

def download_audio(video_url: str, output_name: str, artist_name: str):
    """Downloads YouTube video as ALAC audio with metadata."""
    output_file = os.path.join(BASE_DIRECTORY, f"{output_name}.%(ext)s")  # Ensures proper extension
    
    yt_dlp_cmd = [
        YT_DLP_PATH, "-x", "--audio-format", "alac",
        "--embed-thumbnail", "--add-metadata", "--embed-chapters",
        "--postprocessor-args", f"-metadata artist='{artist_name}'",
        "-o", output_file, video_url
    ]
    
    print("Downloading audio...")
    try:
        subprocess.run(yt_dlp_cmd, check=True)
        print("Download complete.")
        return os.path.join(BASE_DIRECTORY, f"{output_name}.m4a")
    except subprocess.CalledProcessError as e:
        print(f"Error: yt-dlp failed with code {e.returncode}")
        return None
