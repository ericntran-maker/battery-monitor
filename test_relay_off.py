import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)

print("Relay OFF")
GPIO.output(17, GPIO.LOW)   # Many modules are active LOW
