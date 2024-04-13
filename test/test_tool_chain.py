# test_tool_chain.py - A module to test the function calling tool chain module
from verbalai.tool_chain import ToolChain
import sqlite3
from datetime import datetime
import os
import json
from verbalai.VectorDB import VectorDB
from verbalai.commands import predict_intent
from dotenv import load_dotenv
from verbalai.log_config import setup_logging
from termcolor import colored
import logging
from time import time
import argparse

# Load environment variables and set up logging
load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

# Assuming your SQL files are located in the 'data' directory relative to your script
data_directory = "data"

sql_files = [
    "insert_discussions_categories.sql",
    "insert_dialogue_units.sql",
    "insert_sentiment_scores.sql",
    "insert_dialogue_unit_topics.sql"
]

# Generate a day prefix in the format YYYYMMDD (e.g., 20230408 for April 8, 2023)
# Corrected the strftime directive for hour, minute, and second
day_prefix = datetime.now().strftime('%Y%m%d_%H%M%S')

# Concatenate the day prefix with the base names for the database and index files
db_name = f"{day_prefix}_test_vector_db.sqlite"
index_name = f"{day_prefix}_test_vector_db.ann"

# Assuming VectorDB initializes its SQLite connection internally,
# we can use sqlite3 directly to execute our SQL files against the database.
def execute_sql_files(db_path, sql_files):
    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Iterate over and execute each SQL file
    for sql_file in sql_files:
        file_path = os.path.join(data_directory, sql_file)
        with open(file_path, 'r') as file:
            sql_script = file.read()
            cursor.executescript(sql_script)
    
    # Close the connection
    conn.close()

# Initialize the VectorDB instance with the prefixed file names
vector_db = VectorDB(db_path=db_name, index_path=index_name)

# Create a tool chain instance, to be initialized in the main function
tool_chain = None


def find_discussions(kwargs):
    try:
        discussions = vector_db.find_discussions(**kwargs)
        return f"Search results: {[vector_db.retrieve_discussion_by_id(id) for id in discussions]}", True
        #return f"Search results: {[{key: value for key, value in vector_db.retrieve_discussion_by_id(id).items() if key in ["discussion_id", "title", "starttime"]} for id in discussions]}", True
    except Exception as e:
        return f"There was a problem on finding the discussions; {e}", False


def find_dialogue_units(kwargs):
    try:
        dialogues, distances = vector_db.find_dialogue_units(**kwargs)
        return f"Search results: {[vector_db.retrieve_dialogue_unit_by_id(id) for id in dialogues]}", True
    except Exception as e:
        return f"There was a problem on finding the dialogue units; {e}", False


def retrieve_discussion_by_id(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"], include_random=True)
        discussion = vector_db.retrieve_discussion_by_id(kwargs["discussion_id"])
        return f"Discussion details: {discussion}", True
    except Exception as e:
        return f"There was a problem on retrieving the discussion; {e}", False


def retrieve_dialogue_unit_by_id(kwargs):
    try:
        dialogue = vector_db.retrieve_dialogue_unit_by_id(kwargs["dialogue_unit_id"])
        return f"Dialogue unit details: {dialogue}", True
    except Exception as e:
        return f"There was a problem on retrieving the dialogue unit; {e}", False


def remove_category(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.remove_category(**kwargs)
        categories = vector_db.retrieve_categories(kwargs["discussion_id"])
        return f"Discussion category has been removed successfully. Categories for the modified discussion are currently: {categories}", True
    except Exception as e:
        return f"There was a problem on removing the category from the discussion; {e}", False


def modify_discussion(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.modify_discussion(**kwargs)
        discussion = vector_db.retrieve_discussion_by_id(kwargs["discussion_id"])
        return f"Discussion name|featured flag has been modified successfully. Discussion details are currently: {discussion}", True
    except Exception as e:
        return f"There was a problem on modifying the discussion; {e}", False


def assign_category(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.assign_category(**kwargs)
        categories = vector_db.retrieve_categories(kwargs["discussion_id"])
        return f"Category has been assigned to the discussion successfully. Categories for the modified discussion are currently: {categories}", True
    except Exception as e:
        return f"There was a problem on assigning category to the discussion; {e}", False


callbacks = {
    "assign_category": lambda kwargs: assign_category(kwargs),
    "modify_discussion": lambda kwargs: modify_discussion(kwargs),
    "remove_category": lambda kwargs: remove_category(kwargs),
    "retrieve_dialogue_unit_by_id": lambda kwargs: retrieve_dialogue_unit_by_id(kwargs),
    "retrieve_discussion_by_id": lambda kwargs: retrieve_discussion_by_id(kwargs),
    "find_discussions": lambda kwargs: find_discussions(kwargs),
    "find_dialogue_units": lambda kwargs: find_dialogue_units(kwargs)
}


def summarize_results(correct_predictions, low_confidence_predictions, incorrect_predictions, failed_tool_executions, times):
    total_tests = correct_predictions + low_confidence_predictions + incorrect_predictions + failed_tool_executions
    
    if total_tests == 0:
        print("\nSummary:")
        print("    No test phrases were processed.")
        print("    Used tokens: 0")
        print("    Cost: $0")
        return
    
    average_time = sum(times) / len(times) if times else 0
    print("\nSummary:")
    print(f"    Total test phrases: {total_tests}")
    print(f"    Correct predictions: {correct_predictions} ({correct_predictions/total_tests*100:.2f}%)")
    print(f"    Low confidence predictions: {low_confidence_predictions} ({low_confidence_predictions/total_tests*100:.2f}%)")
    print(f"    Incorrect predictions: {incorrect_predictions} ({incorrect_predictions/total_tests*100:.2f}%)")
    print(f"    Failed tool executions: {failed_tool_executions} ({failed_tool_executions/total_tests*100:.2f}%)")
    print(f"    Average execution time: {average_time:.4f} seconds")
    print(f"    Used tokens:", tool_chain.get_token_usage())
    print(f"    Cost: $", tool_chain.get_cost())


def main_loop(args):
    
    correct_predictions = 0
    low_confidence_predictions = 0
    incorrect_predictions = 0
    failed_tool_executions = 0
    times = []
    
    test_files = ["assign_category", "modify_discussion", "remove_category", "retrieve_dialogue_unit_by_id", "retrieve_discussion_by_id", "find_discussions", "find_dialogue_units"]
    
    test_files = ["assign_category"]
    
    # Test the tools with the expected tool names
    for expected_tool in test_files:
        test_file = f"data/{expected_tool}_tests.json"
        # If file does not exist, continue
        if not os.path.isfile(test_file):
            print(f"No test data found for tool: {expected_tool}")
            continue
        
        print(f"\n-----Testing tool: {expected_tool}-----")
        # Load test data from the corresponding json file
        with open(test_file, "r") as file:
            test_data = json.load(file)
            for test in test_data:
                
                tool_name = expected_tool
            
                success = False
                start_time = time()
                
                predicted_tool, confidence, _ = predict_intent(test["prompt"], args.model_path)
                
                if tool_name in callbacks and confidence < args.low_confidence_threshold:
                    print(f"\n{colored('?', 'yellow')} Low confidence in tool prediction: {predicted_tool} with confidence {confidence:.2f}. Command will not be executed.")
                    low_confidence_predictions += 1
                elif tool_name != "" and predicted_tool != tool_name:
                    print(f"\n{colored('✗', 'red')} Prediction mismatch: entered '{tool_name}', predicted '{predicted_tool}' with confidence {confidence:.2f}. Command will not be executed.")
                    incorrect_predictions += 1
                elif predicted_tool in callbacks:
                    try:
                        response, success = tool_chain.exec(predicted_tool, test["prompt"], callbacks, test["args"] if args.test_args else {})
                        if success:
                            print(f"\n{colored('✓', 'green')} {response}")
                            correct_predictions += 1
                        else:
                            print(f"\n{colored('✗', 'red')} Error executing tool: {predicted_tool}. Error: {response}")
                            failed_tool_executions += 1
                    except Exception as e:
                        print(f"\n{colored('✗', 'red')} Error executing tool: {predicted_tool}. Error: {e}")
                        failed_tool_executions += 1
                else:
                    print("\nTool not found. Please enter a valid tool name.")
                
                execution_time = time() - start_time
                times.append(execution_time)
                log_data = {
                    "expected_tool": tool_name,
                    "prompt": test["prompt"],
                    "predicted_tool": predicted_tool,
                    "confidence": confidence,
                    "success": success,
                    "execution_time": execution_time
                }
                logger.info(log_data)
    
    summarize_results(correct_predictions, low_confidence_predictions, incorrect_predictions, failed_tool_executions, times)


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Interactively test and train a tool prediction model by processing user input commands and comparing the expected tool against the predicted tool.")
    
    parser.add_argument("-lct", "--low_confidence_threshold", type=float, default=0.9, help="Threshold below which predictions are considered to have low confidence and are not executed.")
    parser.add_argument("-m", "--model_path", type=str, default="models/vai_model", help="Path to the intent prediction model.")
    parser.add_argument("-ta", "--test_args", action="store_true", help="Should the application test the arguments passed to the tool?")
    parser.add_argument("-gm", "--gpt_model",  type=str, default="claude-3-haiku-20240307", help="Claude GPT model to use for retrieving tool arguments.")
    
    args = parser.parse_args()
    
    print("\nSelected arguments for this session:")
    print(f"    Low confidence threshold: {args.low_confidence_threshold}")
    print(f"    Model path: {args.model_path}")
    print(f"    Test arguments: {args.test_args}")
    
    # Execute SQL files to populate the test database
    execute_sql_files(db_name, sql_files)
    
    # Initialize the tool chain with the selected GPT model
    tool_chain = ToolChain(model=args.gpt_model)
    
    # Create a new session for the discussion
    # Discussion is created without a title
    # After the first dialogue insert we could update the title
    # automaticly with a name describing the initial prompts
    session_id = vector_db.create_new_session()
    current_discussion_id = vector_db.current_discussion_id

    # This is just for showing the user that connections are ready
    print("\nNew session", session_id, "created! Current discussion ID:", current_discussion_id)
    
    main_loop(args)
