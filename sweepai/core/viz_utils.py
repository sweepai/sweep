def print_bar_chart(data: dict[str, list]):
    total_length = sum(len(v) for v in data.values())
    max_bar_length = 50
    
    # Sort the data based on the values in descending order
    sorted_data = sorted(data.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Find the length of the longest category name
    max_category_length = max(len(key) for key in data.keys())
    
    for key, value in sorted_data:
        value = len(value)
        ratio = value / total_length
        bar_length = int(ratio * max_bar_length)
        bar = '█' * bar_length
        print(f"{key.ljust(max_category_length)} | {bar} {value}")