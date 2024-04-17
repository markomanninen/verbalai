# gpt_token_calculator.py - A module
# Prices for input and output tokens per million tokens in dollars
# as per 2024-04-16
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
    },
    "gpt-4-0125-preview": {
        "input": 10.00,  # $10 / MTok
        "output": 30.00  # $30 / MTok
    },
    "gpt-4-1106-preview": {
        "input": 10.00,  # $10 / MTok
        "output": 30.00  # $30 / MTok
    },
    "gpt-4-1106-vision-preview": {
        "input": 10.00,  # $10 / MTok
        "output": 30.00  # $30 / MTok
    },
    "gpt-4-turbo": {
        # 128k
        "input": 10.00,  # $10 / MTok
        "output": 30.00  # $30 / MTok
    },
    "gpt-4-turbo-2024-04-09": {
        # 128k
        "input": 10.00,  # $10 / MTok
        "output": 30.00  # $30 / MTok
    },
    "gpt-4": {
        "input": 30.00,  # $30 / MTok
        "output": 60.00  # $60 / MTok
    },
    "gpt-4-0314": {
        "input": 30.00,  # $30 / MTok
        "output": 60.00  # $60 / MTok
    },
    "gpt-4-32k": {
        "input": 60.00,  # $60 / MTok
        "output": 120.00  # $120 / MTok
    },
    "gpt-4-32k-0314": {
        "input": 60.00,  # $60 / MTok
        "output": 120.00  # $120 / MTok
    },
    "gpt-3.5-turbo": {
        "input": 3.00,  # $3 / MTok
        "output": 6.00  # $6 / MTok
    },
    "gpt-3.5-turbo-0125": {
        "input": 0.50,  # $0.50 / MTok
        "output": 1.50  # $1.50 / MTok
    },
    "gpt-3.5-turbo-1106": {
        "input": 1.00,  # $1 / MTok
        "output": 2.00  # $2 / MTok
    },
    "gpt-3.5-turbo-0613": {
        "input": 1.50,  # $1.50 / MTok
        "output": 2.00  # $2 / MTok
    },
    "gpt-3.5-turbo-16k-0613": {
        "input": 3.00,  # $3 / MTok
        "output": 4.00  # $4 / MTok
    },
    "gpt-3.5-turbo-0301": {
        "input": 1.50,  # $1.50 / MTok
        "output": 2.00  # $2 / MTok
    },
    "gpt-3.5-turbo-instruct": {
        "input": 1.50,  # $1.50 / MTok
        "output": 2.00  # $2 / MTok
    }
}

class GPTTokenCalculator:
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.cost = 0.0

    def update_token_counts(self, message, model, response = ""):
        """Update the token counts based on a message."""
        # Anthropic models
        if hasattr(message, 'usage') and 'claude' in model:
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens
        # OpenAI models
        elif hasattr(message, 'usage') and 'gpt' in model:
            # Extract total token usage
            total_tokens_used = message['usage']['total_tokens']

            # Calculate output tokens. In estimate, token is 4 characters.
            self.total_output_tokens += len(response)/4
            
            # Calculate input tokens
            self.total_input_tokens += total_tokens_used - self.total_output_tokens
            
        self.cost += token_prices[model]['input'] * (self.total_input_tokens / 1000000)
        self.cost += token_prices[model]['output'] * (self.total_output_tokens / 1000000)


    def get_token_usage(self):
        """Get the total sum of input and output tokens."""
        return self.total_input_tokens + self.total_output_tokens
    
    def get_cost(self):
        """The the total cost of the used input and output tokens."""
        if self.get_token_usage() == 0:
            return 0.0
        else:
            return round(self.cost, 3) if self.cost > 0.001 else 0.001
