import eel

def main():
    # Initialize Eel with the 'web' folder as the web root.
    eel.init('web')

    # Start Eel, using 'main.html' as the main page.
    eel.start('main.html')

# Call the main function.
if __name__ == '__main__':
    main()