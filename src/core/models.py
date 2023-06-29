import random

def select_model():
    """
    This function randomly selects between the models: GPT4 and GPT4-0613 for both the normal and 32k versions.
    """
    models = ["gpt-4", "gpt-4-32k", "gpt-4-0613", "gpt-4-32k-0613"]
    selected_model = random.choice(models)
    return selected_model
