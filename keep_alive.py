import os
import threading
from flask import Flask
import logging

logger = logging.getLogger('YuZhongBot')

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask_server():
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Keep-alive web server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = threading.Thread(target=run_flask_server)
    t.daemon = True
    t.start()
    logger.info("Keep-alive web server thread started.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    keep_alive()
    import time
    time.sleep(30)
