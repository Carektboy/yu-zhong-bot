import keep_alive
import discord
import os
from dotenv import load_dotenv

from bardapi import Bard
import requests
from io import BytesIO

# Start the Flask web server for Render's keep-alive health checks in a separate thread
keep_alive.run()

# Load environment variables (for local testing, Render uses its own configured env vars)
load_dotenv() 

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

# Configure Discord Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # Required for reading message content
intents.members = True # Required for on_member_join event
intents.guilds = True # Required for guild events like on_member_join

client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)

# Load personality from file
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "You are a helpful AI assistant." # Default personality if file not found
    print("WARNING: personality.txt not found. Using default personality.")

# Function to generate image using Hugging Face API
def generate_image(prompt):
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2",
            headers={"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"},
            json={"inputs": prompt}
        )
        if response.status_code == 200:
            return BytesIO(response.content)
        else:
            print(" Hugging Face Error:", response.text)
            return None
    except Exception as e:
        print(" Image Gen Error:", e)
        return None

# Discord Event: Bot is ready
@client.event
async def on_ready():
    print(f"Yu Zhong has awakened! Logged in as {client.user} (ID: {client.user.id})")
    print("------")

# Discord Event: Message received
@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Basic command handling (adjust as needed for your specific commands)
    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')

    # Example: Respond to a command for Bard (Bard Token needed)
    if message.content.startswith('!bard'):
        if BARD_TOKEN:
            prompt = message.content[len('!bard '):].strip()
            if prompt:
                try:
                    response_content = bard.get_answer(prompt)['content']
                    await message.channel.send(f"Bard's response: {response_content}")
                except Exception as e:
                    await message.channel.send(f"An error occurred with Bard: {e}")
                    print(f"Bard API error: {e}")
            else:
                await message.channel.send("Please provide a prompt for Bard.")
        else:
            await message.channel.send("Bard API token is not configured.")

    # Example: Generate an image (Hugging Face Token needed)
    if message.content.startswith('!image'):
        if HUGGINGFACE_TOKEN:
            image_prompt = message.content[len('!image '):].strip()
            if image_prompt:
                await message.channel.send(f"Generating image for: '{image_prompt}'... This may take a moment.")
                image_data = generate_image(image_prompt)
                if image_data:
                    await message.channel.send(file=discord.File(image_data, "generated_image.png"))
                else:
                    await message.channel.send("Failed to generate image. Check logs for details.")
            else:
                await message.channel.send("Please provide a prompt for the image.")
        else:
            await message.channel.send("Hugging Face API token is not configured for image generation.")

# Discord Event: Member joins the guild
@client.event
async def on_member_join(member):
    # Example: Send a welcome message to a specific channel
    # Replace 'YOUR_WELCOME_CHANNEL_ID' with the actual ID of your welcome channel
    welcome_channel_id = 123456789012345678 # Replace with your channel ID
    welcome_channel = client.get_channel(welcome_channel_id)
    if welcome_channel:
        await welcome_channel.send(f"Welcome to the server, {member.mention}! Yu Zhong welcomes you.")
    else:
        print(f"Warning: Welcome channel with ID {welcome_channel_id} not found.")


# -----------------------------------------------------------
# CRITICAL DEBUGGING BLOCK - DO NOT REMOVE UNTIL BOT IS ONLINE
# -----------------------------------------------------------
print("Attempting to run client.run(DISCORD_TOKEN)") # New log
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN is None! Bot cannot connect.") # New log if token is missing
else:
    try:
        client.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Bot login failed! This usually means the DISCORD_TOKEN is invalid or expired.") # New specific error log
    except discord.HTTPException as e:
        print(f"ERROR: Discord HTTP Exception during login: {e} (Check bot permissions/API limits or Discord status).")
    except Exception as e:
        print(f"ERROR: An unexpected exception occurred during client.run(): {e}") # Catch all other errors
print("client.run() call finished or failed to start.") # This indicates the bot process exited or disconnected.
# -----------------------------------------------------------
