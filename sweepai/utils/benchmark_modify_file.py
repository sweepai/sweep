import time
from sweepai.core.sweep_bot import SweepBot

def benchmark_modify_file(file_path):
    # Open and read the file
    with open(file_path, 'r') as file:
        file_contents = file.read()

    # Record the start time
    start_time = time.time()

    # Call the process_file function
    sweep_bot = SweepBot()
    sweep_bot.process_file(file_contents)

    # Record the end time
    end_time = time.time()

    # Calculate and print the execution time
    execution_time = end_time - start_time
    print(f"The modify_file function took {execution_time} seconds to execute.")

if __name__ == "__main__":
    benchmark_modify_file("sweepai/core/sweep_bot.py")

