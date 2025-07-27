import os
import threading
from flask import Flask
import logging

# Configure a logger for this module
logger = logging.getLogger('YuZhongBot')

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask_server():
    # Render sets the PORT environment variable for web services
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Keep-alive web server starting on port {port}")
    # We set debug=False for production environments
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = threading.Thread(target=run_flask_server)
    t.daemon = True # Allows the main program to exit even if the thread is still running
    t.start()
    logger.info("Keep-alive web server thread started.")

if __name__ == '__main__':
    # This block is for testing keep_alive.py directly
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    keep_alive()
    print("Flask server started. Press Ctrl+C to exit.")
    # Keep the main thread alive for a bit to see the Flask server start
    import time
    time.sleep(30) # Sleep for a short while to allow server to initialize
