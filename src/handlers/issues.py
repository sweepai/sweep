from src.core.sweep_bot import SweepBot

def process_issue_labels(title: str, labels: list[str]):
    bot = SweepBot()
    processed_title = bot.process_issue_title(title)
    # Pass the processed title and labels to the bot
    bot.input(processed_title, labels)