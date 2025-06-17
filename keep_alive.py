from flask import Flask
from threading import Thread
import asyncio

# Import the update function from your updater script
try:
    from update_patch_notes import main as update_patch_notes_main
except ImportError:
    update_patch_notes_main = None  # Safe fallback if file is missing

app = Flask('')

@app.route('/')
def home():
    return "Yu Zhong lives."

@app.route('/update-patch')
def update_patch():
    if update_patch_notes_main is None:
        return "Patch update script not found.", 500
    try:
        asyncio.run(update_patch_notes_main())
        return "✅ Patch notes updated!", 200
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
