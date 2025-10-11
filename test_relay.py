import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)

print("Relay ON")
GPIO.output(17, GPIO.HIGH)   # Many modules are active LOW
