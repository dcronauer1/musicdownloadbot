import discord
import os
import asyncio

from discord import app_commands
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters,apply_manual_timestamps_to_file
from utils import ask_confirmation, run_command, find_file_case_insensitive, get_entries_from_json

BASE_DIRECTORY = config["download_settings"]["base_directory"]
FILE_EXTENSION = config["download_settings"]["file_extension"]

# Custom Bot class to sync slash commands on startup.
class MyBot(commands.Bot):
    async def setup_hook(self):
        # This will sync slash commands with Discord
        await self.tree.sync()

# Enable necessary intents
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent

# Create bot instance with updated intents
bot = MyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="download", description="Download a video, extract chapters, and send metadata to Discord")
async def download(interaction: discord.Interaction, link: str, title: str = None, artist: str = None, tags: str = None, date: str = None,
         type: str = "Song", addtimestamps: bool = False):
    """
    Slash command to download a video.
    
    :param link: The URL of the YouTube video.
    :param title: Custom title for the output file and metadata title
    :param artist: Artist name for metadata. Checked against a list to see if it already exists
    :param tags: Formatted as tag1,tag2,..., with .strip() being used (so tag1, tag2,... is fine) Checked against a list to see if they already exist
    :param date: _____________
    :param type: (Song|Playlist): ____
    :param addtimestamps: if True, prompt for timestamps. Default False
    
    The 'interaction' object is similar to 'ctx' in prefix commands, 
    containing information about the command invocation.
    """
    # Send an initial response.
    await interaction.response.defer()  # Acknowledge the command first

    # Download the audio in a separate thread
    audio_file = await download_audio(interaction, link, title, artist, tags)
    
    if not audio_file:
        await interaction.followup.send("❗Failed to download audio.")
        return
    timestamps = None
    if addtimestamps: #addtimestamps true, use user timestamps
        timestamps = await ask_for_timestamps(interaction)  # Prompt user for timestamps
        await apply_manual_timestamps_to_file(timestamps,audio_file)
        timestamp_file = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
    else:
        timestamp_file = await extract_chapters(audio_file)    #get timestamps
    if timestamp_file == None:  #no timestamps, prompt user
        #prompt user defined templates 
        if (await ask_confirmation(interaction, "Would you like to add timestamps?")):
            timestamps = await ask_for_timestamps(interaction)  # Prompt user for timestamps
            await apply_manual_timestamps_to_file(timestamps,audio_file)
            timestamp_file = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
    if timestamp_file:
        # Extract chapters using musicolet_timestamp_converter.py
        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
    else:   
        await interaction.followup.send("🎊Audio downloaded without chapters.")


"""Replace commands"""
replace_group = app_commands.Group(name="replace", description="replace related commands")

@replace_group.command(name="timestamps", description="Replace timestamps on an already existing audio file")
async def replace_timestamps(interaction: discord.Interaction, title: str):
    """
    Replace timestamps on an already existing audio file

    :param title: Title of the output file. Case insensitive
    """
    audio_file = find_file_case_insensitive(BASE_DIRECTORY,f"{title}{FILE_EXTENSION}") #get file, ignore casing of input
    if audio_file == None:    #check if file exists
        #NOTE: could have an issue here with split playlists if i put them in sub directories (just add a variable ig?)
        await interaction.followup.send("❗File does not exist")
        await interaction.followup.send(f"List of files: {os.listdir(BASE_DIRECTORY)}")   #send all files to user
        ################# NOTE: add a check here for similar files
        return
    
    timestamps = await ask_for_timestamps(interaction)  # Prompt user for timestamps
    await apply_manual_timestamps_to_file(timestamps,audio_file)
    timestamp_file = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
    if timestamp_file:
        # Extract chapters using musicolet_timestamp_converter.py
        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
    else:   
        await interaction.followup.send("🎊Audio downloaded without chapters.")

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
    
"""List commands"""
list_group = app_commands.Group(name="list", description="List related commands")

@list_group.command(name="music", description="list all music files")
async def list_music(interaction: discord.Interaction):
    """function to list all music"""
    # Use the initial response method
    music_files = [f for f in os.listdir(BASE_DIRECTORY)]
    if not music_files:
        await interaction.response.send_message("No music files found.")
    else:
        await interaction.response.send_message(f"List of music: {', '.join(music_files)}")

@list_group.command(name="artists", description="list all authors in use")
async def list_artists(interaction: discord.Interaction):
    """function to list all authors that are stored"""
    await interaction.response.send_message(f"List of authors: {get_entries_from_json('artists.json')}")

@list_group.command(name="tags", description="list all tags in use")
async def list_tags(interaction: discord.Interaction):
    """function to list all tags that are stored"""
    await interaction.response.send_message(f"List of tags: {get_entries_from_json('tags.json')}")

bot.run(config["bot_settings"]["BOT_TOKEN"])