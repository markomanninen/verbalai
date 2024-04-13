# interactive_tool_trainer.py - A module to train and test the tool chain module
# Native modules
import os
import sqlite3
import logging
import argparse
from time import time
from datetime import datetime
# Thirdparty modules
from termcolor import colored
from dotenv import load_dotenv
# Verbalai modules
from verbalai.tool_chain import ToolChain
from verbalai.VectorDB import VectorDB
from verbalai.commands import predict_intent
from verbalai.log_config import setup_logging

# Load environment variables and set up logging
load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

# Assuming your SQL files are located in the 'data' directory relative to your script
data_directory = "data"

# To insert example data for the tests
sql_files = [
    "insert_discussions_categories.sql",
    "insert_dialogue_units.sql",
    "insert_sentiment_scores.sql",
    "insert_dialogue_unit_topics.sql"
]

# Generate a day prefix in the format YYYYMMDD (e.g., 20240408 for April 8, 2024)
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

# Create a new tool chain instance
tool_chain = ToolChain()

def find_discussions(kwargs):
    try:
        discussions = vector_db.find_discussions(**kwargs)
        return f"Search results: {[vector_db.retrieve_discussion_by_id(id) for id in discussions]}", True
        #return f"Search results: {[{key: value for key, value in vector_db.retrieve_discussion_by_id(id).items() if key in ["discussion_id", "title", "starttime"]} for id in discussions]}", True
    except Exception as e:
        return f"There was a problem on finding the discussions; {e}", False


def find_dialogue_units(kwargs):
    try:
        # This method potentially uses vector database to find similar documents, thus
        # distances are returned as well.
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
    
    while True:
        try:
            user_input = input("\nEnter command in the format 'tool_name:prompt' or just 'prompt'. Type 'exit' to close.\n> ")
            if user_input.lower() == 'exit':
                break
            
            parts = user_input.split(':', 1)
            
            if len(parts) == 2:
                tool_name, prompt = parts
                tool_name = tool_name.strip()
                prompt = prompt.strip()
            elif len(parts) == 1:
                # Assume default tool name if none provided
                tool_name = ''  # Replace 'default_tool' with your actual default tool name
                prompt = parts[0].strip()
            else:
                print("\nInvalid input format. Please use the format 'tool_name:prompt' or just 'prompt'.")
                continue
            
            # If no tool name is provided, use the predicted tool name as the tool name
            if prompt == "":
                prompt = tool_name
            
            if tool_name == "" and prompt == "":
                print("\nInvalid input format. Please use the format 'tool_name:prompt' or just 'prompt'.")
                continue
            
            success = False
            start_time = time()
            
            predicted_tool, confidence, _ = predict_intent(prompt, args.model_path)
            
            if (tool_name == "" or tool_name in callbacks) and confidence < args.low_confidence_threshold:
                print(f"\n{colored('?', 'yellow')} Low confidence in tool prediction: {predicted_tool} with confidence {confidence:.2f}. Command will not be executed.")
                low_confidence_predictions += 1
            elif tool_name != "" and predicted_tool != tool_name:
                print(f"\n{colored('✗', 'red')} Prediction mismatch: entered '{tool_name}', predicted '{predicted_tool}' with confidence {confidence:.2f}. Command will not be executed.")
                incorrect_predictions += 1
            elif tool_name == "" or predicted_tool in callbacks:
                try:
                    response, success = tool_chain.exec(predicted_tool, prompt, callbacks)
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
                "prompt": prompt,
                "predicted_tool": predicted_tool,
                "confidence": confidence,
                "success": success,
                "execution_time": execution_time
            }
            logger.info(log_data)
            
        except KeyboardInterrupt:
            break
    
    summarize_results(correct_predictions, low_confidence_predictions, incorrect_predictions, failed_tool_executions, times)


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Interactively test and train a tool prediction model by processing user input commands and comparing the expected tool against the predicted tool.")
    parser.add_argument("-lct", "--low_confidence_threshold", type=float, default=0.9, help="Threshold below which predictions are considered to have low confidence and are not executed.")
    parser.add_argument("-m", "--model_path", type=str, default="models/vai_model", help="Path to the intent prediction model.")
    args = parser.parse_args()

    print("Welcome to the Interactive Tool Trainer.")
    print("You can enter commands in the format 'tool_name:prompt' or just 'prompt' in order to bypass the tool name test.")
    print("Example: 'retrieve_discussion_by_id:I'm looking for the specifics of the first discussion in the system; can you pull up the information?'")
    print("To exit, type 'exit'.")
    
    print("\nSelected arguments for this session:")
    print(f"Low confidence threshold: {args.low_confidence_threshold}")
    print(f"Model path: {args.model_path}")
    
    # Execute SQL files to populate the test database
    execute_sql_files(db_name, sql_files)
    
    # Create a new session for the discussion
    # Discussion is created without a title
    # After the first dialogue insert we could update the title
    # automaticly with a name describing the initial prompts
    session_id = vector_db.create_new_session()
    current_discussion_id = vector_db.current_discussion_id

    # This is just for showing the user that connections are ready
    print("New session", session_id, "created! Current discussion ID:", current_discussion_id)
    
    main_loop(args)
