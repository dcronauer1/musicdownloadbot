import discord
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters,apply_manual_timestamps_to_file
from utils import ask_confirmation, run_command

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
    
    Parameters:
    - link: The URL of the YouTube video.
    - title: Custom title for the output file.
    - artist: Artist name for metadata. Checked against a list to see if it already exists
    - tags: tags. formatted as tag1,tag2,..., with .strip() being used (so tag1, tag2,... is fine) Checked against a list to see if they already exist
    - date: _____________
    - timestamps: formatted as min:sc "title"
    - type: (Song|Playlist):
    
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

    timestamp_file = await extract_chapters(interaction, audio_file)

    if timestamp_file == None or timestamps:
        #prompt user defined templates
        if timestamps: #timestamps not empty, use user timestamps
            apply_manual_timestamps_to_file(timestamps,audio_file)
            timestamp_file = await extract_chapters(interaction, audio_file)    #convert user provided timestamps to .txt 
        elif (await ask_confirmation(interaction, "Would you like to add timestamps?")):
            ##########need to prompt for timestamps here
            #timestamps=
            apply_manual_timestamps_to_file(timestamps,audio_file)
            timestamp_file = await extract_chapters(interaction, audio_file)    #convert user provided timestamps to .txt
    if timestamp_file:
        # Extract chapters using musicolet_timestamp_converter.py
        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
    else:   
        await interaction.followup.send("🎊Audio downloaded without chapters.")

# Example of a simple slash command that sends a message.
@bot.tree.command(name="hello", description="Replies with a greeting.")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello! This is a sample command.")

bot.run(config["bot_settings"]["BOT_TOKEN"])
