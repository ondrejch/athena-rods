from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.core.virtual import viewport
from luma.led_matrix.device import max7219
from luma.core.legacy import text
from luma.core.legacy.font import proportional, CP437_FONT, LCD_FONT
import time

serial = spi(port=0, device=0, gpio=noop())
device = max7219(serial, rotate=1)
device.contrast(10)
virtual = viewport(device, width=200, height=400)
device.clear()  # Turns off all LEDs

def displayRectangle():
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white", fill="white")

def displayLetter():
    with canvas(device) as draw:
        text(draw, (0, 0), "A", fill="white", font=proportional(CP437_FONT))

def scrollToDisplayText(my_text: str = "Hello, Nice to meet you!"):
    with canvas(virtual) as draw:
        text(draw, (0, 0), my_text, fill="white", font=proportional(CP437_FONT))
    for offset in range(150):
        virtual.set_position((offset,0))
        time.sleep(0.1)

def arrowUp(move: int = 0, h: int = -1): 
    with canvas(device) as draw:
       draw.line((2, 0 + move, 2, 4 + move), fill=1)
       draw.line((2, 0 + move, 0, 2 + move), fill=1)
       draw.line((2, 0 + move, 4, 2 + move), fill=1)
       if h >= 0:
           draw.line((7, 7, 7, 7 - h), fill=1)

def arrowDown(move: int = 0, h: int = -1): 
    with canvas(device) as draw:
       draw.line((2, 4 + move, 2, 0 + move), fill=1)
       draw.line((2, 4 + move, 0, 2 + move), fill=1)
       draw.line((2, 4 + move, 4, 2 + move), fill=1)
       if h >= 0:
           draw.line((7, 7, 7, 7 - h), fill=1)

def notMoving(h: int = -1): 
    with canvas(device) as draw:
       draw.line((0, 2, 4, 2), fill=1)
       draw.line((0, 4, 4, 4), fill=1)
       if h >= 0:
           draw.line((7, 7, 7, 7 - h), fill=1)

def startUp():
    for i in range(8):
        with canvas(device) as draw:
            draw.rectangle( (1, 7-i, 6, 7), outline="white", fill="white")
        time.sleep(float(i)/20.0+0.05)

def shutDown():
    for i in range(8):
        with canvas(device) as draw:
            draw.rectangle( (1, i, 6, 7), outline="white", fill="white")
        time.sleep(0.1)
    device.clear()  # Turns off all LEDs


def main():
    while True:
        #scrollToDisplayText("Welcome, Ondrej!")
        startUp()
        arrowUp(1, 1)
        time.sleep(0.2)
        arrowUp(0 ,1)
        print('a')
        time.sleep(.5)
        arrowDown(0)
        time.sleep(0.2)
        arrowDown(1)
        notMoving()
        time.sleep(1)
        print('a')        
        time.sleep(.5)
        shutDown()
        time.sleep(.5)


def oldmain():
    while True:
        displayRectangle()
        print('a')
        time.sleep(9)
        displayLetter()
        print('a')
        time.sleep(2)
        scrollToDisplayText()
        print('b')

def destroy():
    pass

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        destroy()
