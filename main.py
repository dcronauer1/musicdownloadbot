import discord
import os
import asyncio
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters,apply_manual_timestamps_to_file
from utils import ask_confirmation, run_command, find_file_case_insensitive

BASE_DIRECTORY = config["download_settings"]["base_directory"]
FILE_EXTENSION = config["download_settings"]["file_extension"]

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
async def download(interaction: discord.Interaction, link: str, title: str = None, artist: str = None, tags: str = None, date: str = None,
                   timestamps: str = None, type: str = "Song"):
    """
    Slash command to download a video.
    
    :param link: The URL of the YouTube video.
    :param title: Custom title for the output file.
    :param artist: Artist name for metadata. Checked against a list to see if it already exists
    :param tags: tags. formatted as tag1,tag2,..., with .strip() being used (so tag1, tag2,... is fine) Checked against a list to see if they already exist
    :param date: _____________
    :param timestamps: formatted as min:sc "title"
    :param type: (Song|Playlist):
    
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

    if timestamps != None: #timestamps not empty, use user timestamps
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


@bot.tree.command(name="replace_timestamps", description="Replace timestamps on an already existing audio file")
async def replace_timestamps(interaction: discord.Interaction, title: str, timestamps: str):
    """
    Replace timestamps on an already existing audio file
    """
    audio_file = find_file_case_insensitive(BASE_DIRECTORY,f"{title}{FILE_EXTENSION}") #get file, ignore casing of input
    if audio_file == None:    #check if file exists
        #NOTE: could have an issue here with split playlists if i put them in sub directories (just add a variable ig?)
        await interaction.followup.send("❗File does not exist")
        ################# add a check here for similar files and/or to print a list
        return
    
    await apply_manual_timestamps_to_file(timestamps,audio_file)
    timestamp_file = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
    if timestamp_file:
        # Extract chapters using musicolet_timestamp_converter.py
        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
    else:   
        await interaction.followup.send("🎊Audio downloaded without chapters.")


async def ask_for_timestamps(interaction: discord.Interaction) -> str:
    await interaction.followup.send("⏳ Please enter the timestamps in the format `min:sec \"title\"` (one per line):")

    def check(msg: discord.Message):
        return msg.author == interaction.user and msg.channel == interaction.channel

    try:
        response = await bot.wait_for("message", check=check, timeout=120)  # Wait for 2 minutes
        return response.content
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ You took too long to respond. Skipping timestamp entry.")
        return None

# Example of a simple slash command that sends a message.
@bot.tree.command(name="hello", description="Replies with a greeting.")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello! This is a sample command.")

bot.run(config["bot_settings"]["BOT_TOKEN"])
