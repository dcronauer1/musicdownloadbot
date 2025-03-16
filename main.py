import discord
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters
import asyncio


# Confirmation view using Discord UI buttons
class ConfirmView(discord.ui.View):
    def __init__(self, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None  # Will be set to True/False based on user's choice

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.send_message("Confirmed!", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.send_message("Canceled.", ephemeral=True)

async def ask_confirmation(interaction: discord.Interaction, details: str) -> bool:
    """
    Sends a confirmation prompt with the given details.
    Returns True if the user confirms; False if canceled.
    """
    view = ConfirmView()
    await interaction.response.send_message(
        f"Please confirm the following details:\n{details}",
        view=view,
        ephemeral=True  # Only the command user sees this
    )
    await view.wait()  # Wait for the user to respond
    return view.value

# Custom Bot class to sync slash commands on startup.
class MyBot(commands.Bot):
    async def setup_hook(self):
        # This will sync your slash commands with Discord
        await self.tree.sync()

# Create bot instance with default intents.
bot = MyBot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

async def download_wrapper(*args):
    return await asyncio.to_thread(download_audio, *args)

# Slash command: /download
@bot.tree.command(name="download", description="Download a video, extract chapters, and send metadata to Discord")
async def download(interaction: discord.Interaction, link: str, title: str = None, artist: str = None, tags: str = None):
    """
    Slash command to download a video.
    
    Parameters:
    - link: The URL of the YouTube video.
    - title: Custom title for the output file.
    - artist: Artist name for metadata. Checked against a list to see if it already exists
    - tags: tags. formatted as tag1,tag2,..., with .strip() being used (so tag1, tag2,... is fine) Checked against a list to see if they already exist
    
    The 'interaction' object is similar to 'ctx' in prefix commands, 
    containing information about the command invocation.
    """
    # Send an initial response.
    await interaction.response.defer()  # Acknowledge the command first

    # Download the audio in a separate thread
    audio_file = await download_wrapper(link, title, artist, tags)
    
    if not audio_file:
        await interaction.followup.send("Failed to download audio.")
        return

    # Extract chapters using musicolet_timestamp_converter.py
    chapter_file = extract_chapters(audio_file)
    if chapter_file:
        await interaction.followup.send("Chapters saved! Uploading file...", file=discord.File(chapter_file))
    else:
        await interaction.followup.send("No chapters found.")

# Example of a simple slash command that sends a message.
@bot.tree.command(name="hello", description="Replies with a greeting.")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello! This is a sample command.")

bot.run(config["bot_settings"]["BOT_TOKEN"])
