#!/usr/bin/env python3

from typing import Optional, List
import time
import smbus2 as smbus
import subprocess

BUS = smbus.SMBus(1)

def write_word(addr: int, data: int) -> None:
	"""Write a word to a specified address with optional bit adjustment based on global BLEN setting.
	Parameters:
	- addr (int): The address to which the data should be written.
	- data (int): The data value to be written, which may be modified based on BLEN.
	Returns:
	- None: This function does not return a value."""
	global BLEN
	temp = data
	if BLEN == 1:
		temp |= 0x08
	else:
		temp &= 0xF7
	BUS.write_byte(addr ,temp)

def send_command(comm: int) -> None:
	# Send bit7-4 firstly
	"""Sends a command to an LCD over I2C by splitting it into two 4-bit transfers.
	Parameters:
	- comm (int): The command byte to be sent to the LCD.
	Returns:
	- None: This function does not return a value."""
	buf = comm & 0xF0
	buf |= 0x04               # RS = 0, RW = 0, EN = 1
	write_word(LCD_ADDR ,buf)
	time.sleep(0.002)
	buf &= 0xFB               # Make EN = 0
	write_word(LCD_ADDR ,buf)

	# Send bit3-0 secondly
	buf = (comm & 0x0F) << 4
	buf |= 0x04               # RS = 0, RW = 0, EN = 1
	write_word(LCD_ADDR ,buf)
	time.sleep(0.002)
	buf &= 0xFB               # Make EN = 0
	write_word(LCD_ADDR ,buf)

def send_data(data: int) -> None:
	# Send bit7-4 firstly
	"""Sends 8-bit data to the LCD by writing high and low nibble separately.
	Parameters:
	- data (int): 8-bit data value to be sent to the LCD.
	Returns:
	- None: This function does not return any value."""
	buf = data & 0xF0
	buf |= 0x05               # RS = 1, RW = 0, EN = 1
	write_word(LCD_ADDR ,buf)
	time.sleep(0.002)
	buf &= 0xFB               # Make EN = 0
	write_word(LCD_ADDR ,buf)

	# Send bit3-0 secondly
	buf = (data & 0x0F) << 4
	buf |= 0x05               # RS = 1, RW = 0, EN = 1
	write_word(LCD_ADDR ,buf)
	time.sleep(0.002)
	buf &= 0xFB               # Make EN = 0
	write_word(LCD_ADDR ,buf)

def i2c_scan() -> List[str]:
    cmd = "i2cdetect -y 1 |awk \'NR>1 {$1=\"\";print}\'"
    result = subprocess.check_output(cmd, shell=True).decode()
    result = result.replace("\n", "").replace(" --", "")
    i2c_list = result.split(' ')
    return i2c_list

def init(addr: Optional[int] = None, bl: int = 1) -> None:
	"""Initializes the LCD with the specified I2C address and backlight setting.
	Parameters:
	- addr (int, optional): I2C address of the LCD. Defaults to None, which attempts to auto-detect address 0x27 or 0x3f.
	- bl (int): Backlight setting, where 1 is on and 0 is off. Defaults to 1.
	Returns:
	- bool: True if initialization is successful, otherwise False."""
	global LCD_ADDR
	global BLEN

	i2c_list = i2c_scan()
	# print(f"i2c_list: {i2c_list}")

	if addr is None:
		if '27' in i2c_list:
			LCD_ADDR = 0x27
		elif '3f' in i2c_list:
			LCD_ADDR = 0x3f
		else:
			raise IOError("I2C address 0x27 or 0x3f no found.")
	else:
		LCD_ADDR = addr
		if str(hex(addr)).strip('0x') not in i2c_list:
			raise IOError(f"I2C address {str(hex(addr))} or 0x3f no found.")

	BLEN = bl
	try:
		send_command(0x33) # Must initialize to 8-line mode at first
		time.sleep(0.005)
		send_command(0x32) # Then initialize to 4-line mode
		time.sleep(0.005)
		send_command(0x28) # 2 Lines & 5*7 dots
		time.sleep(0.005)
		send_command(0x0C) # Enable display without cursor
		time.sleep(0.005)
		send_command(0x01) # Clear Screen
		BUS.write_byte(LCD_ADDR, 0x08)
	except:
		return False
	else:
		return True

def clear() -> None:
	send_command(0x01) # Clear Screen

def openlight() -> None:  # Enable the backlight
	BUS.write_byte(0x27,0x08)
	BUS.close()

def write(x: int, y: int, str: str) -> None:
	"""Positions the cursor at coordinates (x, y) on a display and writes a given string.
	Parameters:
	- x (int): The horizontal position on the display, limited to the range 0-15.
	- y (int): The vertical position on the display, limited to the range 0-1.
	- str (str): The string to be written starting at position (x, y).
	Returns:
	- None: The function sends data to the display without returning a value."""
	if x < 0:
		x = 0
	if x > 15:
		x = 15
	if y <0:
		y = 0
	if y > 1:
		y = 1

	# Move cursor
	addr = 0x80 + 0x40 * y + x
	send_command(addr)

	for chr in str:
		send_data(ord(chr))

if __name__ == '__main__':
	init(0x27, 1)
	write(4, 0, 'Hello')
	write(7, 1, 'world!')

