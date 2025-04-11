import discord
import asyncio
import os
import re
import json
import grp
import sys
from config_manager import config
from typing import Optional

FILE_EXTENSION = config["download_settings"]["file_extension"]

# Confirmation view using Discord UI buttons
class ConfirmView(discord.ui.View):
    def __init__(self, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None  # Will be set to True/False based on user's choice

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.send_message("✅Confirmed!", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.send_message("❌Canceled.", ephemeral=True)

async def ask_confirmation(interaction: discord.Interaction, details: str) -> bool:
    """
    Sends a confirmation prompt with the given details.
    Returns True if the user confirms; False if canceled or timed out.
    """
    view = ConfirmView()
    await interaction.followup.send(
        f"**Please confirm the following details:**\n{details}",
        view=view,
        ephemeral=True  # Only the command user sees this
    )
    await view.wait()  # Wait for the user to respond

    # Default to False (cancel) if the user doesn't interact within the timeout
    if view.value is None:
        view.value = False
        print("User confirm timed out")

    return view.value

async def ask_for_something(interaction: discord.Interaction, something: str) -> Optional[str]:
    """Ask user for content (text or image)"""
    if not interaction.response.is_done():
        await interaction.response.defer()
        
    await interaction.followup.send(
        f"⏳ Please send {something} (text or image attachment):"
    )

    def check(msg: discord.Message):
        return (msg.author == interaction.user and 
                msg.channel == interaction.channel and 
                (msg.content or msg.attachments))

    try:
        response = await interaction.client.wait_for("message", check=check, timeout=120)
        # Prioritize text first
        if response.content:
            print(f"User provided {something} (text): {response.content}")
            return response.content.strip()

        if response.attachments:
            url = response.attachments[0].url
            print(f"User provided {something} (attachment): {url}")
            return url

        return None
    except asyncio.TimeoutError:
        await interaction.followup.send(f"❌ Timed out. Skipping {something} entry.")
        return (None, None)

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

async def apply_thumbnail_to_file(thumbnail_url: str, audio_file: str):
    """Apply a thumbnail to a file using FFMPEG
    
    :param thumbnail: pass in as a link
    :return: True if success, else send error or error code

    """
    # Download the image to a temporary file
    temp_file = "temp_cover.png"
    returncode, _, error = await run_command(f'curl -o "{temp_file}" "{thumbnail_url}"')
    if returncode != 0:#failed
        print(f"❌Thumbnail update failed, curl output: {error}")
        try:
            os.remove(temp_file)
        except OSError as e:
            print(f"Warning: Failed to delete temp file (can ignore this): {e}")
            
        return f"Thumbnail update failed, curl output:\n{error}"

    # FFmpeg command (requires local files)
    ffmpeg_cmd = (
        f'ffmpeg -y -i "{audio_file}" -i "{temp_file}" -map 0:0 -map 1 -c copy -disposition:v attached_pic "temp{FILE_EXTENSION}"'
    )    
    # Execute command using your existing run_command utility
    returncode, _, error = await run_command(ffmpeg_cmd, verbose=True)
    
    os.remove(temp_file)        #remove temp picture

    if returncode == 0:
        #replace file
        returncode, _, error = await run_command(f'mv "temp{FILE_EXTENSION}" "{audio_file}"', verbose=True)
        if returncode == 0:
            print("✅Thumbnail updated successfully")
            return True
        else:
            print(f"❌file replacement failed, error: {error}")
            return f"file replacement failed, error:\n{error}"
    else:
        print(f"❌Thumbnail update failed: {error}")
        return f"ffmpeg error code (error in console):\n{returncode}"

async def apply_timestamps_to_file(timestamps: str, audio_file: str):
    """Convert timestamps to FFmetadata and apply them to an audio file.
    
    :param timestamps: expected to be in the format of [min:sec]"title"
    """
    
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
    ffmpeg_cmd = (
        f'ffmpeg -i "{audio_file}" -i {metadata_file} '
        f'-map_metadata 0 -map_chapters 1 '
        f'-c copy -y "{audio_file}.tmp.{FILE_EXTENSION}" '
        f'&& mv "{audio_file}.tmp.{FILE_EXTENSION}" "{audio_file}"'
    )
    print(f"ffmpeg_cmd = {ffmpeg_cmd}")
    returncode, _, error = await run_command(ffmpeg_cmd, verbose=True)

    if returncode != 0:
        print(f"FFmpeg command failed: {error}")

    # Cleanup metadata and temp.{FILE_EXTENSION} file
    try:
        os.remove(metadata_file)
    except OSError as e:
        print(f"Warning: Failed to delete metadata file: {e}")

async def run_command(command, verbose=False):
    """Run a command asynchronously and optionally stream its output in real-time.
    If verbose=True, then output will print to console
    
    :return: returncode, stdout_lines, stderr_lines
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout_lines = []
    stderr_lines = []

    async def read_stream(stream, line_list):
        buffer = bytearray()
        while True:
            chunk = await stream.read(1024)  # read in 1024 byte chunks
            if not chunk:
                break
            buffer.extend(chunk)
            # Process complete lines from the buffer
            while b'\n' in buffer:
                line, sep, buffer = buffer.partition(b'\n')
                decoded_line = line.decode().strip()
                if verbose:
                    print(decoded_line)  # Only print if verbose is True
                line_list.append(decoded_line)
        # Process any remaining data in the buffer
        if buffer:
            decoded_line = buffer.decode().strip()
            if decoded_line:
                if verbose:
                    print(decoded_line)
                line_list.append(decoded_line)

    # Read both stdout and stderr concurrently
    await asyncio.gather(
        read_stream(process.stdout, stdout_lines),
        read_stream(process.stderr, stderr_lines)
    )

    returncode = await process.wait()  # Wait for process to finish
    return returncode, "\n".join(stdout_lines), "\n".join(stderr_lines)

def find_file_case_insensitive(directory, filename):
    """function to find files of the same name, with different casing, and return the file in use"""
    #first check if exact casing exists already
    fullPath = os.path.join(directory,filename)
    if os.path.exists(fullPath):
        return fullPath
    #next check if same name, different casing exists
    for file in os.listdir(directory):
        if file.lower() == filename.lower():
            return os.path.join(directory, file)
    return None

def get_entries_from_json(filename) -> str:
    """function to return all entries from a json file"""
    if not os.path.exists(filename):
        return "file doesn't exist"
    
    try:
        with open(filename) as file:
            data = json.load(file)
        return data
    except json.JSONDecodeError:
        return "file exists but contains invalid JSON"

def apply_directory_permissions():
    """
    Applies consistent permissions to all files and directories in BASE_DIRECTORY
    based on the configuration settings.

    :return: False if failed, True if success
    """
    if not config["directory_settings"]["keep_perms_consistent"]:
        return False

    base_dir = config["download_settings"]["base_directory"]
    
    # Convert permissions to octal
    file_perms = int(str(config["directory_settings"]["file_perms"]), 8)
    dir_perms = int(str(config["directory_settings"]["directory_perms"]), 8)
    target_group = config["directory_settings"]["group"]

    try:
        gid = grp.getgrnam(target_group).gr_gid
    except KeyError:
        print(f"Group {target_group} not found")
        return False

    for root, dirs, files in os.walk(base_dir):
        for name in dirs + files:
            path = os.path.join(root, name)
            try:
                # Set group ownership first
                os.chown(path, -1, gid)  # -1 preserves current UID
                
                # Set permissions
                mode = dir_perms if os.path.isdir(path) else file_perms
                os.chmod(path, mode)
                
            except PermissionError as e:
                print(f"⚠️Permission denied on {path}: {e}")
            except Exception as e:
                print(f"⚠️Error processing {path}: {e}")
    print("✅Updated file permissions successfully")
    return True