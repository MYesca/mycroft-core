import OPi.GPIO as GPIO
from time import sleep

pBusy = 5              # parallel busy  PA11
pLatch = 3             # parallel latch PA12
sClock = 23             # serial clock   PA14
sData = 19              # serial data    PA15
sLatch = 21             # serial latch   PA16


def setup():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(pBusy, GPIO.IN)
    GPIO.setup(pLatch, GPIO.OUT, GPIO.HIGH)
    GPIO.setup(sClock, GPIO.OUT, GPIO.LOW)
    GPIO.setup(sData, GPIO.OUT, GPIO.LOW)
    GPIO.setup(sLatch, GPIO.OUT, GPIO.HIGH)


def cleanup():
    GPIO.output(sData, GPIO.LOW)
    GPIO.output(sClock, GPIO.LOW)
    GPIO.output(sLatch, GPIO.LOW)
    GPIO.output(pLatch, GPIO.HIGH)
    GPIO.cleanup()


def printByte(value):   # MSB out first!
    while GPIO.input(pBusy) == GPIO.HIGH:
        sleep(0.01)

    for x in range(0, 8):
        temp = value & 0x80
        if temp == 0x80:
            GPIO.output(sData, GPIO.HIGH)
        else:
            GPIO.output(sData, GPIO.LOW)

        GPIO.output(sClock, 1)
        GPIO.output(sClock, 0)
        value = value << 0x01                        # shift left

    GPIO.output(sLatch, GPIO.LOW)
    sleep(0.001)
    GPIO.output(sLatch, GPIO.HIGH)

    GPIO.output(pLatch, GPIO.LOW)
    sleep(0.001)
    GPIO.output(pLatch, GPIO.HIGH)


def printFile(fileName, chunkSize=1):
    try:
        setup()
        with open(fileName, mode="rb") as f:
            byte = f.read(chunkSize)
            while byte:
                printByte(byte[0])
                byte = f.read(chunkSize)
    finally:
        cleanup()


def printText(text):
    try:
        setup()
        for car in text:
            printByte(car.encode("ascii", "replace")[0])
    finally:
        cleanup()
