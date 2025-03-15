import discord
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters

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

# Slash command: /download
@bot.tree.command(name="download", description="Download a video, extract chapters, and send metadata to Discord")
async def download(interaction: discord.Interaction, link: str, title: str, artist: str):
    """
    Slash command to download a video.
    
    Parameters:
    - link: The URL of the YouTube video.
    - title: Custom title for the output file.
    - artist: Artist name for metadata.
    
    The 'interaction' object is similar to 'ctx' in prefix commands, 
    containing information about the command invocation.
    """
    # Send an initial response.
    await interaction.response.send_message(f"Downloading `{title}` by `{artist}`...")

    # Download audio file using ytdownloader.py
    audio_file = download_audio(link, title, artist)
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
