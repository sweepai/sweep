import eel

def main():
    # The 'web' folder needs to exist in the project.
    # Initialize Eel with the 'web' folder as the web root.
    eel.init('web')

    # The 'main.html' file needs to exist in the 'web' folder.
    # Start Eel, using 'main.html' as the main page.
    eel.start('main.html')

# Call the main function.
if __name__ == '__main__':
    main()