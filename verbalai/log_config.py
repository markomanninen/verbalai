import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    # Determine the path to the root of the application
    # This assumes the script is in the 'verbalai' directory and the 'logs' directory is at the root
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(root_path, "logs")

    # Ensure the logs directory exists
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    log_filename = os.path.join(logs_dir, "verbalai.log")

    # Configure logging
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        handlers=[
                            RotatingFileHandler(log_filename, maxBytes=10000000, backupCount=5),
                            #logging.StreamHandler()
                        ])

# Only set up logging if no handlers are configured yet
if not logging.getLogger().hasHandlers():
    setup_logging()
