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

async def run_command(command, verbose=False):
    """Run a command asynchronously and optionally stream its output in real-time."""
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
