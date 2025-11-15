#!/usr/bin/env python3
"""Test script to verify inverter reset functionality"""
import RPi.GPIO as GPIO
import time

INVERTER_PIN = 27
RESET_DURATION = 8

def test_inverter_reset():
    print("Testing inverter reset...")
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(INVERTER_PIN, GPIO.OUT, initial=GPIO.LOW)
    
    print(f"✅ Inverter is ON (GPIO {INVERTER_PIN} = LOW)")
    time.sleep(2)
    
    print(f"⚡ Turning inverter OFF for {RESET_DURATION} seconds...")
    GPIO.output(INVERTER_PIN, GPIO.HIGH)
    
    for i in range(RESET_DURATION):
        print(f"   OFF: {i+1}/{RESET_DURATION} seconds")
        time.sleep(1)
    
    print("✅ Turning inverter back ON...")
    GPIO.output(INVERTER_PIN, GPIO.LOW)
    
    print("✅ Test complete - inverter is ON")
    print("\nNote: GPIO cleanup NOT called - pin stays LOW (ON)")

if __name__ == "__main__":
    try:
        test_inverter_reset()
    except KeyboardInterrupt:
        print("\nTest interrupted - ensuring inverter is ON")
        GPIO.output(INVERTER_PIN, GPIO.LOW)
    except Exception as e:
        print(f"Error: {e}")
        try:
            GPIO.output(INVERTER_PIN, GPIO.LOW)
        except:
            pass
