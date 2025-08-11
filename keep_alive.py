import os
import threading
from flask import Flask
import logging

l = logging.getLogger('YuZhongBot')

a = Flask(__name__)

@a.route('/')
def h():
    return "Bot is alive!"

def r():
    p = int(os.environ.get("PORT", 5000))
    l.info(f"Keep-alive web server starting on port {p}")
    a.run(host='0.0.0.0', port=p, debug=False)

def k():
    t = threading.Thread(target=r)
    t.daemon = True
    t.start()
    l.info("Keep-alive web server thread started.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    k()
    import time
    time.sleep(30)
