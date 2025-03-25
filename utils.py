import discord
import asyncio
import os
import json
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
        f"⚠️Please confirm the following details:\n{details}",
        view=view,
        ephemeral=True  # Only the command user sees this
    )
    await view.wait()  # Wait for the user to respond

    # Default to False (cancel) if the user doesn't interact within the timeout
    if view.value is None:
        view.value = False
        print("User confirm timed out")

    return view.value

async def ask_for_timestamps(interaction: discord.Interaction) -> str:
    """Ask user for timestamps."""
    # Only defer if interaction has not been responded to
    if not interaction.response.is_done():
        await interaction.response.defer()

    await interaction.followup.send(
        "⏳ Please enter the timestamps in the format `min:sec \"title\"` (one per line):"
    )

    def check(msg: discord.Message):
        return msg.author == interaction.user and msg.channel == interaction.channel

    try:
        response = await interaction.client.wait_for("message", check=check, timeout=120)  # 2-minute timeout
        print(f"User provided timestamps: {response.content}")
        return response.content
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ You took too long to respond. Skipping timestamp entry.")
        return ""

async def run_command(command, verbose=False):
    """Run a command asynchronously and optionally stream its output in real-time.
    If verbose=True, then output will print to console"""
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