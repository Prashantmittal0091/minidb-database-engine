import sys
import logging
logging.basicConfig(level=logging.INFO)

from minidb.web_server import app

if __name__ == "__main__":
    print("Starting Flask server...", flush=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
