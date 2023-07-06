from tabulate import tabulate

data = [
    ["Name", "Age", "Country"],
    ["John", 25, "USA"],
    ["Alice", 30, "Canada"],
    ["Bob", 35, "Australia"]
]

data = [
    ["Name", "Age"],
    ["John", 25],
    ["Alice", 30],
    ["Bob", 35]
]

table = tabulate(data, headers="firstrow", tablefmt="pipe")

print(table)