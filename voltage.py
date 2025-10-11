#!/usr/bin/env python3
import serial
import os
from config import SERIAL_PORTS, BAUD_RATE

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

try:
    PORT = find_usb_device()
    ser = serial.Serial(PORT, baudrate=BAUD_RATE, timeout=2)

    while True:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line.startswith("V"):
            mv = int(line.split("\t")[1])   # VE.Direct gives mV
            print(f"{mv/1000:.2f} V")
            break
except Exception as e:
    print(f"Error: {e}")
