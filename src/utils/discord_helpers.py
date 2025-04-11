import discord
import asyncio
from config.config_manager import config
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