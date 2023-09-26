import re
import subprocess
from collections import defaultdict

from tqdm import tqdm

# 1. Use ctags to fetch a list of all entities
subprocess.run(["ctags", "-R", "sweepai"])

exports = defaultdict(list)
all_entities = []

with open("tags", "r") as file:
    for line in file:
        if not line.startswith("!"):
            entity, filename = line.split("\t")[:2]
            exports[filename].append(entity)
            all_entities.append(entity)

# 2. Use regex to find all imports
imports = defaultdict(lambda: defaultdict(list))

any_entity_matches = "(?P<entity>" + "|".join(all_entities) + ")"
pattern = f"from\\s+(?P<source>\\S+)\\s+import\\s+{any_entity_matches}"
matcher = re.compile(pattern)

for file, entity_list in tqdm(exports.items()):
    with open(file, "r") as f:
        content = f.read()
        matches = matcher.findall(content)
        print(file, matches)
        for source, entity in matches:
            imports[file][entity].append(entity)
# print(imports)

# # 3. Produce a DAG mapping each entity to references
# dag = defaultdict(lambda: defaultdict(list))

# for file, entities in imports.items():
#     for entity, import_statements in entities.items():
#         for statement in import_statements:
#             reference = re.findall(r"from\s+(\w+)", statement)
#             if reference:
#                 dag[file][entity].append(reference[0])

# # Print the DAG
# for file, entities in dag.items():
#     print(f"File: {file}")
#     for entity, references in entities.items():
#         print(f"  Entity: {entity} -> References: {', '.join(references)}")
