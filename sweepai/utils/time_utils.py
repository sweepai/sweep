import datetime

def time_since(time: datetime.datetime) -> str:
    now = datetime.datetime.now()
    diff = now - time
    seconds = diff.total_seconds()

    if seconds < 60:
        return f"{seconds} seconds ago"
    elif seconds < 3600:
        return f"{seconds // 60} minutes ago"
    elif seconds < 86400:
        return f"{seconds // 3600} hours ago"
    else:
        return f"{seconds // 86400} days ago"
