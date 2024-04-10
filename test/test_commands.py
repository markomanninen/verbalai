# test_commands.py - A module to train and test the commands module
import argparse
# Library imports
from verbalai.commands import train_data, test_commands
# Import log lonfig as a side effect only
from verbalai.log_config import setup_logging
import logging
logger = logging.getLogger(__name__)
log_level = logging.INFO
# Only set up logging if no handlers are configured yet
if not logging.getLogger().hasHandlers():
    setup_logging(log_level)

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Train and test the commands module")
    parser.add_argument("--train", action="store_true", help="Train the data")
    parser.add_argument("--low_confidence_threshold", type=float, default=0.70, help="Threshold for low confidence")
    parser.add_argument("--model_path", type=str, default="model", help="Path to the model")
    parser.add_argument("--train_file", type=str, default="data/train_commands.yaml", help="Path to the train file")
    parser.add_argument("--test_file", type=str, default="data/test_commands.yaml", help="Path to the test file")
    args = parser.parse_args()
    
    if args.train:
        # Train the data
        train_data(file=args.train_file, model_path=args.model_path)

    # Test the commands
    test_commands(file=args.test_file, low_confidence_threshold=args.low_confidence_threshold, model_path=args.model_path)
