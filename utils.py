import discord
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
    await interaction.followup.send(
        f"Please confirm the following details:\n{details}",
        view=view,
        ephemeral=True  # Only the command user sees this
    )
    await view.wait()  # Wait for the user to respond
    return view.value
import asyncio

async def run_command(command):
    """Run a command asynchronously and stream its output in real-time."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout_lines = []
    stderr_lines = []

    # Read and print stdout line by line
    async for line in process.stdout:
        decoded_line = line.decode().strip()
        print(decoded_line)  # Print to console immediately
        stdout_lines.append(decoded_line)

    # Read and print stderr line by line
    async for line in process.stderr:
        decoded_line = line.decode().strip()
        print(decoded_line)  # Print to console immediately
        stderr_lines.append(decoded_line)

    returncode = await process.wait()  # Wait for process to finish
    return returncode, "\n".join(stdout_lines), "\n".join(stderr_lines)
