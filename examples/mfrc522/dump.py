from time import sleep
from mfrc522 import StoreMFRC522
key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


def main():
    reader = StoreMFRC522()
    base_rc522 = reader.reader  # Lower-level access
    print("Hold a tag near the reader")

    while True:

        # Scan for cards
        status, tag = base_rc522.mfrc522_request(base_rc522.PICC_REQIDL)

        # If a card is found
        if status == base_rc522.MI_OK:
            print("Card detected")


        # Get the UID of the card
        status, uid = base_rc522.mfrc522_anticoll()

        # If we have the UID, continue
        if status == base_rc522.MI_OK:
            print(f"Card read UID: {uid}")

            # Select the scanned tag
            base_rc522.mfrc522_select_tag(uid)

            # Dump tag content
            base_rc522.mfrc522_dump_classic_1K(key, uid)

            # Disconnect
            base_rc522.mfrc522_stop_crypto1()

        sleep(1)


if __name__ == '__main__':
    main()

