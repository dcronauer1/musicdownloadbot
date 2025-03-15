import subprocess
import os
from config_manager import config

# Retrieve settings from the JSON configuration
YT_DLP_PATH = config["download_settings"]["yt_dlp_path"]
BASE_DIRECTORY = config["download_settings"]["base_directory"]

def download_audio(video_url: str, output_name: str, artist_name: str):
    """
    Downloads a YouTube video as ALAC audio with embedded metadata.
    
    :param video_url: URL of the YouTube video.
    :param output_name: Base name for the output file.
    :param artist_name: Artist name to embed in metadata.
    :return: The path to the downloaded audio file (assumed to be .m4a) or None if error.
    """
    # Construct the output file template; yt-dlp will append the proper extension.
    output_file_template = os.path.join(BASE_DIRECTORY, f"{output_name}.%(ext)s")
    
    yt_dlp_cmd = [
        YT_DLP_PATH, "-x", "--audio-format", "alac",
        "--embed-thumbnail", "--add-metadata", "--embed-chapters",
        "--postprocessor-args", f"-metadata artist='{artist_name}'",
        "-o", output_file_template,
        video_url
    ]
    
    print("Downloading audio...")
    try:
        subprocess.run(yt_dlp_cmd, check=True)
        print("Download complete.")
        # The converted file should be .m4a, as specified by yt-dlp.
        return os.path.join(BASE_DIRECTORY, f"{output_name}.m4a")
    except subprocess.CalledProcessError as e:
        print(f"Error: yt-dlp failed with code {e.returncode}")
        return None
