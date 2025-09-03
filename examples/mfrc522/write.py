from time import sleep
from mfrc522 import StoreMFRC522


def main():
    """Main function to write input text to an RFID tag using a StoreMFRC522 reader.
    Parameters:
        None
    Returns:
        None
    Example:
        User inputs text to be written to the RFID tag. The application continuously prompts the user to hold a tag near the reader. Once a tag is detected, it displays the tag's ID and the written text, then repeats the process."""
    reader = StoreMFRC522()
    text: str = input('Text to write to your tag: ')
    while True:
        print("Hold a tag near the reader")
        tag_id, text = reader.write(text)
        print(f'ID: {tag_id}\nText: {text}')
        sleep(1)


if __name__ == '__main__':
    main()
