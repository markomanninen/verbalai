# commands.py - A module to train and predict intents from text commands
import yaml
import time
import torch
import numpy as np
from transformers import (
    BertTokenizer, 
    BertForSequenceClassification, 
    Trainer, 
    TrainingArguments
)
from termcolor import colored
from torch.utils.data import Dataset
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

# Library imports
# Import log lonfig as a side effect only
from .log_config import setup_logging
import logging
logger = logging.getLogger(__name__)

# Categories in the order of the training data
# See data/train_commands.yaml
LABEL_DICT = {
    'assign_category': 0, 
    'modify_discussion': 1, 
    'remove_category': 2, 
    'retrieve_dialogue_unit_by_id': 3, 
    'retrieve_discussion_by_id': 4, 
    'find_discussions': 5, 
    'find_dialogue_units': 6
}

def load_data(file_path):
    """Load the data from the given file."""
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
    phrases = []
    intent_labels = []
    label_dict = {}
    for intent, examples in data['commands'].items():
        if intent not in label_dict:
            label_dict[intent] = len(label_dict)
        for example in examples:
            phrases.append(example)
            intent_labels.append(label_dict[intent])
    return phrases, intent_labels, label_dict

# Define the dataset
class IntentDataset(Dataset):
    """Dataset for intent classification."""
    def __init__(self, texts, labels, tokenizer):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = self.texts[idx]
        label = self.labels[idx]
        inputs = self.tokenizer(
            text, 
            padding='max_length', 
            truncation=True, 
            return_tensors="pt", 
            max_length=512
        )
        input_ids = inputs['input_ids'][0]
        attention_mask = inputs['attention_mask'][0]
        return {
            'input_ids': input_ids, 
            'attention_mask': attention_mask, 
            'labels': torch.tensor(label)
        }

# Train and evaluate the model
def train_evaluate_model(phrases, intent_labels, label_dict, model_path):
    """Train and evaluate the model."""
    # Split the dataset
    X_train, X_val, y_train, y_val = train_test_split(phrases, intent_labels, test_size=0.2, random_state=42)

    # Initialize tokenizer and datasets
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
    train_dataset = IntentDataset(X_train, y_train, tokenizer)
    val_dataset = IntentDataset(X_val, y_val, tokenizer)

    # Initialize model
    model = BertForSequenceClassification.from_pretrained('bert-base-uncased', num_labels=len(label_dict))

    # Training arguments
    training_args = TrainingArguments(
        output_dir='./results',
        num_train_epochs=8,
        per_device_train_batch_size=8,
        logging_dir='./logs',
        logging_steps=10,
        #gradient_accumulation_steps=4
    )

    # Train
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset
    )
    
    trainer.train()
    
    model.save_pretrained(model_path)
    tokenizer.save_pretrained(model_path)

    # Evaluate
    predictions = trainer.predict(val_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=1)
    # Find unique labels present in the predictions and the ground truth
    unique_labels = np.unique(np.concatenate((y_val, pred_labels)))

    # Generate target names based on actual labels present, ensuring alignment
    actual_target_names = [label for label, idx in sorted(label_dict.items(), key=lambda item: item[1]) if idx in unique_labels]

    # Ensure labels parameter includes all unique labels present in predictions and ground truth
    labels = sorted(np.unique(np.concatenate((y_val, pred_labels))))

    print(classification_report(y_val, pred_labels, labels=labels, target_names=actual_target_names, zero_division=0))


def predict_intent(text, model_path):
    """Predict the intent of the given text."""
    # Load the trained model and tokenizer
    tokenizer = BertTokenizer.from_pretrained(model_path)
    model = BertForSequenceClassification.from_pretrained(model_path)

    # Assuming you have the label_dict that maps numerical labels to intent names
    # Example label_dict (ensure this matches your training labels)
    label_dict = LABEL_DICT

    # Encode the text using the tokenizer
    inputs = tokenizer(text, padding=True, truncation=True, max_length=512, return_tensors="pt")
    
    # Move inputs to the same device as the model
    inputs = {key: value.to(model.device) for key, value in inputs.items()}
    
    # Predict
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Get the prediction probability
    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    # Convert the numerical label to the intent name
    prediction = np.argmax(probs.detach().numpy(), axis=1)[0]
    predicted_intent = {value: key for key, value in label_dict.items()}[prediction]
    predicted_item = probs[0][prediction].item()
    
    return predicted_intent, predicted_item, prediction

def train_data(file='./data/train_commands.yaml', model_path='model'):
    """Train the model on the training data."""
    phrases, intent_labels, label_dict = load_data(file)
    train_evaluate_model(phrases, intent_labels, label_dict, model_path)

def test_commands(file='./data/test_commands.yaml', low_confidence_threshold=0.70, model_path='model'):
    """Test the model on the test data with informative output format and a summary at the end."""
    test_phrases, intent_labels, label_dict = load_data(file)
    logger.info(f"Loaded {len(test_phrases)} test phrases")
    times = []
    
    # Initialize counters
    correct_predictions = 0
    low_confidence_predictions = 0
    incorrect_predictions = 0

    for expected_intent, phrase in zip(intent_labels, test_phrases):
        start_time = time.time()
        predicted_intent, confidence, prediction = predict_intent(phrase, model_path)
        end_time = time.time()
        times.append(end_time - start_time)
        expected_intent_label = next((key for key, value in label_dict.items() if value == expected_intent), None)
        
        # Update counters based on the outcome
        if predicted_intent == expected_intent_label and confidence >= low_confidence_threshold:
            status_symbol = colored('✓', 'green')
            correct_predictions += 1
        elif confidence < low_confidence_threshold:
            status_symbol = colored('?', 'yellow')
            low_confidence_predictions += 1
        else:
            status_symbol = colored('✗', 'red')
            incorrect_predictions += 1
        
        print(f"{status_symbol} Phrase: {phrase}\n    Expected: {expected_intent_label}\n    Predicted: {predicted_intent}, Confidence: {confidence:.2f}\n")
    
    # Print the summary
    average_time = np.mean(times)
    print("Summary:")
    print(f"    Total test phrases: {len(test_phrases)}")
    print(f"    Correct predictions: {correct_predictions} ({correct_predictions/len(test_phrases)*100:.2f}%)")
    print(f"    Low confidence predictions: {low_confidence_predictions} ({low_confidence_predictions/len(test_phrases)*100:.2f}%)")
    print(f"    Incorrect predictions: {incorrect_predictions} ({incorrect_predictions/len(test_phrases)*100:.2f}%)")
    print(f"    Average prediction time: {average_time:.4f} seconds\n")
    
    logger.info(f"Average prediction time: {average_time:.4f} seconds")