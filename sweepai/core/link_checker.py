import os
import requests
import re

def get_markdown_files(directory):
    markdown_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.md') or file.endswith('.mdx'):
                markdown_files.append(os.path.join(root, file))
    return markdown_files

def extract_links(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    links = re.findall(r'\((http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)\)', content)
    return links

def check_link(url):
    response = requests.get(url)
    return response.status_code == 404

def fix_link(file_path, old_link, new_link):
    with open(file_path, 'r') as file:
        content = file.read()
    content = content.replace(old_link, new_link)
    with open(file_path, 'w') as file:
        file.write(content)

def main():
    markdown_files = get_markdown_files('docs')
    for file in markdown_files:
        links = extract_links(file)
        for link in links:
            if check_link(link):
                # TODO: Determine the correct URL to replace the broken link
                new_link = 'https://example.com'
                fix_link(file, link, new_link)

if __name__ == '__main__':
    main()
