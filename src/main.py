import discord
import os
import asyncio
from typing import Optional

from discord import app_commands
from discord.ext import commands
from config.config_manager import config
from utils.ytdownloader import *
from utils.metadata import *
from utils.discord_helpers import *
from utils.metadata import *
from utils.file_handling import *

BASE_DIRECTORY = config["download_settings"]["base_directory"]
FILE_EXTENSION = config["download_settings"]["file_extension"]

# Custom Bot class to sync slash commands on startup.
class MyBot(commands.Bot):
    async def setup_hook(self):
        # Add command groups BEFORE syncing
        self.tree.add_command(ReplaceGroup())
        self.tree.add_command(ListGroup())
        await self.tree.sync()  # Sync with current command tree

# Enable necessary intents
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent

# Create bot instance with updated intents
bot = MyBot(command_prefix="!", intents=intents)

@bot.tree.command(name="download", description="Download a video, extract chapters, and send metadata to Discord")
async def download(interaction: discord.Interaction, link: str, type: str = "Song", title: str = None, artist: str = None, tags: str = None,
        album: str = None, date: str = None, addtimestamps: bool = None, usedatabase: str = '', excludetracknumsforplaylist: bool = False):
    """
    Slash command to download a video.
    
    :param link: The URL of the YouTube video.
    :param type: (song|album_playlist|playlist) Default song. album_playlist downloads a playlist as one file
    :param title: Custom title for the output file and metadata title
    :param artist: Artist name for metadata. Checked against a list to see if it already exists
    :param tags: Formatted as tag1,tag2,..., with .strip() being used (so tag1, tag2,... is fine) Checked against a list to see if they already exist
    :param album: album name. Must be supplied when type=playlist for track numbers
    :param date: *_____________
    :param addtimestamps: True: add custom timestamps. False: Do not add timestamps (even if included in video). Default None
    :param usedatabase: options (comma separated): (cover|tracktimes|tracknames). Use database for metadata instead of youtube information
    :param excludetracknumsforplaylist: applies when type=playlist: if True: dont add track numbers. Default=False
    
    The 'interaction' object is similar to 'ctx' in prefix commands, containing information about the command invocation.
    """
    # Send an initial response.
    await interaction.response.defer()  # Acknowledge the command first
    
    type = type.lower()
    if type == "album":
        type = "album_playlist"
    if type not in ["song", "album_playlist", "playlist"]:
        await interaction.followup.send(f'❗"{type}" is not a valid type. Valid types are either song, album_playlist, or playlist')
        return
    
    usedatabase = usedatabase.lower()

    timestamps = None
    if addtimestamps: #addtimestamps true, ask user for timestamps before downloading
        timestamps = await ask_for_something(interaction,"timestamps")  # Prompt user for timestamps
    # Download the audio in a separate thread
    audio_file,error_str = await download_audio(interaction, link, type, title, artist, tags, album, addtimestamps, usedatabase, excludetracknumsforplaylist)
    if not audio_file:
        await safe_send(interaction,f"❗Failed to download audio. Error:\n{error_str}")
        return
    
    if timestamps and (type != "playlist"): #if timestamps exist, then user entered timestamps, so use those
        success, error_str = await apply_timestamps_to_file(timestamps,audio_file)
        if(success == False):
            await safe_send(interaction,f"❗Failed to apply chapters: {error_str}")
            return    
                
    if(type != "playlist"):
        timestamp_file,error_str = await extract_chapters(audio_file)    #get timestamps (either user or embedded in video)
    else:
        timestamp_file,error_str=None,"type = Playlist"

    #if no timestamp file, then no timestamps exist, so prompt user. UNLESS user entered False for adding timestamps
    if (timestamp_file == None) and (addtimestamps != False) and (type != "playlist"):
        #prompt user defined templates 
        if (await ask_confirmation(interaction, "Would you like to add timestamps?")):
            timestamps = await ask_for_something(interaction,"timestamps")  # Prompt user for timestamps
            success, error_str = await apply_timestamps_to_file(timestamps,audio_file)
            if(success == False):
                await safe_send(interaction,f"❗Failed to apply chapters: {error_str}")   
                return
            timestamp_file,error_str = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
    
    if timestamp_file:
        # Chapters were extracted using extract_chapters()
        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
    else:   
        await safe_send(interaction,f"🎊Audio downloaded without chapters:\n{error_str}")
    
    apply_directory_permissions()    #update perms if enabled
    return

"""Replace commands"""
class ReplaceGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="replace", description="replace commands")

    async def _get_audio_file(self, interaction: discord.Interaction, title: str) -> Optional[str]:
        """Shared method to find audio file and handle missing files"""
        audio_file = find_file_case_insensitive(BASE_DIRECTORY, f"{title}{FILE_EXTENSION}")
        if not audio_file:    #check if file exists
            tree = save_music_tree(BASE_DIRECTORY)
            await interaction.followup.send("❗File does not exist. Available songs:",file=discord.File(tree))
            return None
        return audio_file

    @app_commands.command(name="timestamps", description="Replace timestamps on an already existing audio file")
    async def replace_timestamps(self, interaction: discord.Interaction, title: str, remove: bool = False):
        """
        Replace timestamps on an already existing audio file

        :param title: Title of the output file. Case insensitive
        :param remove: True: will remove timestamps from files
        """
        # Defer first to prevent interaction token expiration
        await interaction.response.defer()
        
        try:
            #get audio file & check for existence
            audio_file = await self._get_audio_file(interaction, title)
            if audio_file == None:
                return
            
            if remove:
                success, error_str = await apply_timestamps_to_file(None,audio_file,remove)
                if(success):
                    chapter_file = audio_file.replace(f"{FILE_EXTENSION}", ".txt")
                    if os.path.exists(chapter_file):
                        os.remove(chapter_file)
                    await interaction.followup.send("🎊Chapters removed successfully!")
                else:
                    await safe_send(interaction,f"❗Failed to remove chapters: {error_str}")  
                    return          
            else:
                timestamps = await ask_for_something(interaction, "timestamps")  # Prompt user for timestamps
                success, error_str = await apply_timestamps_to_file(timestamps,audio_file,remove)
                if(success):
                    timestamp_file, err = await extract_chapters(audio_file)    #convert user provided timestamps to .txt
                    if timestamp_file:
                        # Extract chapters using musicolet_timestamp_converter.py
                        await interaction.followup.send("🎊Chapters saved! Uploading file...", file=discord.File(timestamp_file))
                    else:   
                        await safe_send(interaction,f"❗No timestamp file generated: {err}")
                        return
                else:
                    await safe_send(interaction,f"❗Failed to apply chapters: {error_str}")            
        except Exception as e:
            await safe_send(interaction,f"❌Error: {str(e)}")
        apply_directory_permissions()    #update perms if enabled
        return
        
    @app_commands.command(name="thumbnail", description="Replace thumbnail on an already existing audio file")
    async def replace_thumbnail(self, interaction: discord.Interaction, title: str, 
                                usedatabase: bool = False, artist: str = None):
        """
        Replace thumbnail/cover on an already existing audio file

        :param title: Title of the output file. Case insensitive
        :param usedatabase: pull the image from a database, instead of using the user's image. Default False
        :param artist: manual fill for usedatabase (ignore unless needed)

        """
        # Defer first to prevent interaction token expiration
        await interaction.response.defer()

        #get audio file & check for existence
        audio_file = await self._get_audio_file(interaction, title)
        if audio_file == None:
            return
        
        if usedatabase:
            metadata = await get_audio_metadata(audio_file)
            if artist == None:
                artist = metadata.get('artist', None)
            if artist == None:
                await interaction.followup.send("⚠️ Unknown artist, please supply one manually")
                return
            cover_url, _, error = await fetch_musicbrainz_data(artist, title)
            if error:
                await safe_send(interaction,f"❌Database lookup failed: {error}")
                return

            if not cover_url:
                await interaction.followup.send("❌No artwork found in database")
                return

            result = await apply_thumbnail_to_file(cover_url, audio_file)
            
            if result is True:
                await interaction.followup.send("🎊Thumbnail updated from MusicBrainz!")
            else:
                await safe_send(interaction,f"❗Error applying thumbnail:\n{result}")
                return
        else:
            thumbnail_url = await ask_for_something(interaction, "thumbnail")

            if thumbnail_url:
                error = await apply_thumbnail_to_file(thumbnail_url, audio_file)
                if (error == True):
                    await interaction.followup.send("🎊Thumbnail saved!")
                else:   
                    await safe_send(interaction,f"❗Thumbnail did not apply properly:\n{error}")             
        
        apply_directory_permissions()    #update perms if enabled
        return

"""List commands"""
class ListGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="list", description="List related commands")

    @app_commands.command(name="music", description="list all music files")
    async def list_music(self, interaction: discord.Interaction):
        """function to list all music"""
        tree = save_music_tree(BASE_DIRECTORY)
        await interaction.response.send_message(file=discord.File(tree))
        return

    @app_commands.command(name="artists", description="list all authors in use")
    async def list_artists(self, interaction: discord.Interaction):
        """function to list all authors that are stored"""
        await interaction.response.send_message(f"List of authors: {get_entries_from_json('artists.json')}")

    @app_commands.command(name="tags", description="list all tags in use")
    async def list_tags(self, interaction: discord.Interaction):
        """function to list all tags that are stored"""
        await interaction.response.send_message(f"List of tags: {get_entries_from_json('tags.json')}")


@bot.event
async def on_ready():
    # Remove the command group additions and sync from here
    apply_directory_permissions()
    print(f"Logged in as {bot.user}")

bot.run(config["bot_settings"]["BOT_TOKEN"])