from time import sleep
from mfrc522 import StoreMFRC522


def main():
    reader = StoreMFRC522()
    while True:
        print("Hold a tag near the reader")
        tag_id, text = reader.read()
        print(f'ID: {tag_id}\nText: {text}')
        sleep(1)

if __name__ == '__main__':
    main()

