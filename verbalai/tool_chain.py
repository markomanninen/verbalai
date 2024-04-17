# tool_chain.py - A module to chain AI chat function calling tools together
from anthropic import Anthropic
from verbalai.claude_tools import schemas
from dotenv import load_dotenv
from verbalai.log_config import setup_logging
import logging

# Load environment variables and set up logging
load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

# Prices for input and output tokens per million tokens in dollars
# as per 2024-04-10
token_prices = {
    "claude-3-haiku-20240307": {
        "input": 0.25,  # $0.25 / MTok
        "output": 1.25  # $1.25 / MTok
    },
    "claude-3-sonnet-20240229": {
        "input": 3.00,  # $3 / MTok
        "output": 15.00  # $15 / MTok
    },
    "claude-3-opus-20240229": {
        "input": 15.00,  # $15 / MTok
        "output": 75.00  # $75 / MTok
    }
}

class ToolChain:
    def __init__(self, model="claude-3-haiku-20240307"):
        self.gpt_client = Anthropic()
        self.model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.cost = 0.0
        self.inference_message_word_count = 0

    def _update_token_counts(self, message):
        """Update the token counts based on a message."""
        if hasattr(message, 'usage'):
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens
            self.cost += token_prices[self.model]['input'] * (self.total_input_tokens / 1000000)
            self.cost += token_prices[self.model]['output'] * (self.total_output_tokens / 1000000)

    def get_tool_messages(self, tool_name, text, callbacks):

        self.inference_message_word_count = 0

        tool_config = schemas.get(tool_name)

        if not tool_config:
            logger.error(f"Tool configuration for '{tool_name}' not found.")
            return None
        
        messages = [{"role": "user", "content": [{"type": "text", "text": text}]}]

        tool_message = self.gpt_client.beta.tools.messages.create(
            model=self.model,
            messages=messages,
            max_tokens=500,
            temperature=0,
            tools=tool_config
        )

        # Update token counts
        self._update_token_counts(tool_message)

        if tool_message.stop_reason == "tool_use":
            tool_use = next(block for block in tool_message.content if block.type == "tool_use")
            tool_id = tool_use.id
            tool_input = tool_use.input
            
            # This may happen if the tool is general name containing many tools in the configuration
            if tool_name != tool_use.name:
                logger.warn(f"Tool name mismatch: '{tool_name}' != '{tool_use.name}'. Using the latter.")
            
            logger.info(f"Tool '{tool_name}' arguments: '{tool_input}'.")
            
            # Call the callback function for the tool
            tool_answer, success = callbacks[tool_use.name](tool_input)
            
            logger.info(f"Tool '{tool_name}' response ({success}): '{tool_answer}'.")
            
            # Note: Tool schema words count is not included
            self.inference_message_word_count += len(tool_answer.split(" "))
            
            return [
                {"role": "assistant", "content": [
                        {"type": "text", "text": f"Calling tool function: {tool_name}. Input: {tool_input}"}
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"User role: tool. Output: {tool_answer}"}
                    ]
                }
            ], success
        else:
            logger.warn(f"Tool '{tool_name}' was not recognized in this context.")
            raise Exception(f"Tool '{tool_name}' was not recognized in this context.")
    
    def exec(self, tool_name, text, callbacks, test_args = {}):
        
        self.inference_message_word_count = 0
        
        tool_config = schemas.get(tool_name)
        
        if not tool_config:
            logger.error(f"Tool configuration for '{tool_name}' not found.")
            return None

        messages = [{"role": "user", "content": [{"type": "text", "text": text}]}]

        tool_message = self.gpt_client.beta.tools.messages.create(
            model=self.model,
            messages=messages,
            max_tokens=500,
            temperature=0,
            tools=tool_config
        )

        # Update token counts
        self._update_token_counts(tool_message)

        if tool_message.stop_reason == "tool_use":
            tool_use = next(block for block in tool_message.content if block.type == "tool_use")
            tool_id = tool_use.id
            tool_input = tool_use.input
            
            # This may happen if the tool is general name containing many tools in the configuration
            if tool_name != tool_use.name:
                logger.warn(f"Tool name mismatch: '{tool_name}' != '{tool_use.name}'. Using the latter.")
            
            # If test arguments are given, check that the tool input matches
            if test_args:
                if tool_input != test_args:
                    logger.warn(f"Tool '{tool_name}' input mismatch: '{tool_input}' != '{test_args}'.")
                    raise Exception(f"Tool input mismatch: '{tool_input}' != '{test_args}'.")
            
            logger.info(f"Tool '{tool_name}' arguments: '{tool_input}'.")
            
            # Call the callback function for the tool
            tool_answer, success = callbacks[tool_use.name](tool_input)
            
            # Note: Tool schema words count is not included
            self.inference_message_word_count += len(tool_answer.split(" "))
            #self.inference_message_word_count += len(tool_message.content[0].text.split(" "))
            
            messages.extend(
                [
                    {"role": tool_message.role, "content": tool_message.content},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result", 
                                "tool_use_id": tool_id, 
                                "content": [{"type": "text", "text": tool_answer}],
                                "is_error": not success,
                            }
                        ]
                    }
                ]
            )

            # Get the final message
            final_message = self.gpt_client.beta.tools.messages.create(
                model=self.model,
                messages=messages,
                max_tokens=500,
                temperature=0,
                tools=tool_config
            )
            
            # TODO: How about chained tools?
            # For instance, if a result list is given, the next tool could be called on the selected item in the list
            # Also, AI might want to ask verification to continue with the preducted tool rather than selecting itself.
            logger.info(final_message)

            # Update token counts for the final message
            self._update_token_counts(final_message)
            try:
                return next(block for block in final_message.content if block.type == "text").text, success
            except StopIteration:
                logger.error("No content text block found in the final message.")
                return f"Final message content could not be retrieved. Stop reason: {final_message.stop_reason}. However, the tool returned the value: {tool_answer}", success
        else:
            logger.warn(f"Tool '{tool_name}' was not recognized in this context.")
            raise Exception(f"Tool '{tool_name}' was not recognized in this context.")

    def get_token_usage(self):
        """Get the total sum of input and output tokens."""
        return self.total_input_tokens + self.total_output_tokens
    
    def get_cost(self):
        if self.get_token_usage() == 0:
            return 0.0
        else:
            return round(self.cost, 3) if self.cost > 0.001 else 0.001
