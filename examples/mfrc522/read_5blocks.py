from time import sleep
from mfrc522 import StoreMFRC522


def main():
    reader = StoreMFRC522()
    reader.BLOCK_ADDRESSES = {  # Only read 5 blocks
             7: [ 4,  5,  6],
            11: [ 8,  9, 10],
            15: [12, 13, 14],
            19: [16, 17, 18],
            23: [20, 21, 22],
        }
    reader.BLOCK_SLOTS = sum(len(lst) for lst in reader.BLOCK_ADDRESSES.values())

    while True:
        print("Hold a tag near the reader")
        tag_id, text = reader.read()
        print(f'ID: {tag_id}\nText: {text}')
        sleep(1)

if __name__ == '__main__':
    main()

