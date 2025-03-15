import discord
from discord.ext import commands
from config_manager import config
from ytdownloader import download_audio
from musicolet_timestamp_converter import extract_chapters

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def download(ctx, link: str, title: str, artist: str):
    """Downloads a video, extracts chapters, and sends metadata to Discord."""
    await ctx.send(f"Downloading `{title}` by `{artist}`...")

    audio_file = download_audio(link, title, artist)
    if not audio_file:
        await ctx.send("Failed to download audio.")
        return

    chapter_file = extract_chapters(audio_file)
    if chapter_file:
        await ctx.send(f"Chapters saved! Uploading file...")
        await ctx.send(file=discord.File(chapter_file))
    else:
        await ctx.send("No chapters found.")

bot.run(config["bot_settings"]["BOT_TOKEN"])