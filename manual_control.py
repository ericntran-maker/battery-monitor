#!/usr/bin/env python3
"""
Manual control script for testing relay and reading voltage
"""

import RPi.GPIO as GPIO
import serial
import time
import sys
import os
from config import RELAY_PIN, SERIAL_PORTS, BAUD_RATE

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_PIN, GPIO.OUT)

def find_usb_device():
    """Find the first available USB serial device"""
    for port in SERIAL_PORTS:
        if os.path.exists(port):
            try:
                # Try to open the device briefly to verify it's accessible
                test_ser = serial.Serial(port, baudrate=BAUD_RATE, timeout=1)
                test_ser.close()
                print(f"Found available USB device: {port}")
                return port
            except Exception as e:
                print(f"USB device {port} not accessible: {e}")
                continue
        else:
            print(f"USB device {port} does not exist")
    
    # If no devices found, raise an error
    available_ports = [port for port in SERIAL_PORTS if os.path.exists(port)]
    if available_ports:
        error_msg = f"No accessible USB devices found. Available but inaccessible: {available_ports}"
    else:
        error_msg = f"No USB devices found. Checked: {SERIAL_PORTS}"
    
    print(error_msg)
    raise Exception(error_msg)
    
def read_voltage():
    """Read current voltage"""
    try:
        serial_port = find_usb_device()
        ser = serial.Serial(serial_port, baudrate=BAUD_RATE, timeout=2)
        ser.flushInput()
        
        for _ in range(10):
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("V"):
                mv = int(line.split("\t")[1])
                voltage = mv / 1000.0
                ser.close()
                return voltage
        
        ser.close()
        return None
    except Exception as e:
        print(f"Error reading voltage: {e}")
        return None

def connect_charger():
    """Connect charger (relay OFF)"""
    GPIO.output(RELAY_PIN, GPIO.LOW)
    print("✅ Charger CONNECTED (relay OFF)")

def disconnect_charger():
    """Disconnect charger (relay ON)"""
    GPIO.output(RELAY_PIN, GPIO.HIGH)
    print("🔴 Charger DISCONNECTED (relay ON)")

def main():
    setup()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 manual_control.py voltage    - Read current voltage")
        print("  python3 manual_control.py connect    - Connect charger")
        print("  python3 manual_control.py disconnect - Disconnect charger")
        print("  python3 manual_control.py status     - Show voltage and relay status")
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "voltage":
            voltage = read_voltage()
            if voltage:
                print(f"Battery voltage: {voltage:.2f}V")
            else:
                print("Failed to read voltage")
                
        elif command == "connect":
            connect_charger()
            
        elif command == "disconnect":
            disconnect_charger()
            
        elif command == "status":
            voltage = read_voltage()
            if voltage:
                print(f"Battery voltage: {voltage:.2f}V")
                if voltage >= 24.8:
                    print("⚠️  Voltage is HIGH - charger should be disconnected")
                elif voltage <= 24.5:
                    print("✅ Voltage is safe - charger can be connected")
                else:
                    print("🟡 Voltage in hysteresis range")
            else:
                print("Failed to read voltage")
                
        else:
            print(f"Unknown command: {command}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
