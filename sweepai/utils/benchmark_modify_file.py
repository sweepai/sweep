import time
from sweepai.core.sweep_bot import SweepBot, SweepContext
from sweepai.utils.prompt_constructor import HumanMessagePrompt

def benchmark_modify_file(file_path):
    # Open and read the file
    with open(file_path, 'r') as file:
        file_contents = file.read()

    # Create a HumanMessagePrompt object with placeholder values
    human_message = HumanMessagePrompt(
        repo_name="",
        issue_url="",
        username="",
        repo_description="",
        title="",
        summary="",
        snippets=[],
        tree=[],
    )

    # Record the start time
    start_time = time.time()

    # Generate the context for the SweepBot
    context = SweepContext(issue_url="placeholder", use_faster_model=False)
    
    # Call the process_file function with the generated context
    sweep_bot = SweepBot(context=context)
    sweep_bot.process_file(file_contents)

    # Record the end time
    end_time = time.time()

    # Calculate and print the execution time
    execution_time = end_time - start_time
    print(f"The modify_file function took {execution_time} seconds to execute.")

if __name__ == "__main__":
    benchmark_modify_file("sweepai/core/sweep_bot.py")

