#!/usr/bin/env python3
"""
Battery Voltage Monitor with Charger Control
Monitors 6S battery voltage and controls charger relay for safety.

Relay Logic:
- Relay OFF (GPIO.LOW) = Charger ON
- Relay ON (GPIO.HIGH) = Charger OFF (safety disconnect)
"""

import RPi.GPIO as GPIO
import serial
import time
import logging
import os
from datetime import datetime
from config import RELAY_PIN, SERIAL_PORTS, BAUD_RATE
VOLTAGE_THRESHOLD_HIGH = 24.8  # Volts - disconnect charger above this
VOLTAGE_THRESHOLD_LOW = 24.5   # Volts - reconnect charger below this (hysteresis)
MONITOR_INTERVAL = 5           # Seconds between voltage checks

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/erictran/rpi/battery_monitor.log'),
        logging.StreamHandler()
    ]
)

class BatteryMonitor:
    def __init__(self):
        self.setup_gpio()
        self.serial_port = self.find_usb_device()
        self.setup_serial()
        self.charger_connected = True  # Start with charger connected
        self.last_voltage = 0.0
        
    def setup_gpio(self):
        """Initialize GPIO for relay control"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RELAY_PIN, GPIO.OUT)
        # Start with charger connected (relay OFF)
        GPIO.output(RELAY_PIN, GPIO.LOW)
        logging.info("GPIO initialized - Charger connected (relay OFF)")
        
    def find_usb_device(self):
        """Find the first available USB serial device"""
        for port in SERIAL_PORTS:
            if os.path.exists(port):
                try:
                    # Try to open the device briefly to verify it's accessible
                    test_ser = serial.Serial(port, baudrate=BAUD_RATE, timeout=1)
                    test_ser.close()
                    logging.info(f"Found available USB device: {port}")
                    return port
                except Exception as e:
                    logging.debug(f"USB device {port} not accessible: {e}")
                    continue
            else:
                logging.debug(f"USB device {port} does not exist")
        
        # If no devices found, raise an error
        available_ports = [port for port in SERIAL_PORTS if os.path.exists(port)]
        if available_ports:
            error_msg = f"No accessible USB devices found. Available but inaccessible: {available_ports}"
        else:
            error_msg = f"No USB devices found. Checked: {SERIAL_PORTS}"
        
        logging.error(error_msg)
        raise Exception(error_msg)
        
    def setup_serial(self):
        """Initialize serial connection for voltage reading"""
        try:
            self.ser = serial.Serial(self.serial_port, baudrate=BAUD_RATE, timeout=2)
            logging.info(f"Serial connection established on {self.serial_port}")
        except Exception as e:
            logging.error(f"Failed to setup serial connection on {self.serial_port}: {e}")
            raise
            
    def read_voltage(self):
        """Read voltage from VE.Direct protocol"""
        try:
            # Clear any pending data
            self.ser.flushInput()
            
            # Read voltage data
            for _ in range(10):  # Try up to 10 times to get voltage reading
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("V"):
                    mv = int(line.split("\t")[1])  # VE.Direct gives mV
                    voltage = mv / 1000.0
                    self.last_voltage = voltage
                    return voltage
                    
            logging.warning("No voltage reading received")
            return None
            
        except Exception as e:
            logging.error(f"Error reading voltage: {e}")
            return None
            
    def control_charger(self, disconnect=False):
        """Control charger connection via relay"""
        if disconnect and self.charger_connected:
            # Disconnect charger (turn relay ON)
            GPIO.output(RELAY_PIN, GPIO.HIGH)
            self.charger_connected = False
            logging.warning("CHARGER DISCONNECTED - Voltage too high!")
            
        elif not disconnect and not self.charger_connected:
            # Connect charger (turn relay OFF)
            GPIO.output(RELAY_PIN, GPIO.LOW)
            self.charger_connected = True
            logging.info("Charger reconnected - Voltage safe")
            
    def monitor_loop(self):
        """Main monitoring loop"""
        logging.info("Starting battery monitoring...")
        logging.info(f"High voltage threshold: {VOLTAGE_THRESHOLD_HIGH}V")
        logging.info(f"Low voltage threshold: {VOLTAGE_THRESHOLD_LOW}V")
        
        try:
            while True:
                voltage = self.read_voltage()
                
                if voltage is not None:
                    logging.info(f"Battery voltage: {voltage:.2f}V - Charger: {'Connected' if self.charger_connected else 'DISCONNECTED'}")
                    
                    # Safety logic with hysteresis
                    if voltage >= VOLTAGE_THRESHOLD_HIGH:
                        self.control_charger(disconnect=True)
                    elif voltage <= VOLTAGE_THRESHOLD_LOW:
                        self.control_charger(disconnect=False)
                        
                else:
                    logging.warning("Failed to read voltage - maintaining current state")
                    
                time.sleep(MONITOR_INTERVAL)
                
        except KeyboardInterrupt:
            logging.info("Monitoring stopped by user")
        except Exception as e:
            logging.error(f"Monitoring error: {e}")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up GPIO and serial connections"""
        try:
            # Ensure charger is connected before exit (safety)
            GPIO.output(RELAY_PIN, GPIO.LOW)
            GPIO.cleanup()
            self.ser.close()
            logging.info("Cleanup completed - Charger connected")
        except Exception as e:
            logging.error(f"Cleanup error: {e}")

def main():
    """Main function"""
    try:
        monitor = BatteryMonitor()
        monitor.monitor_loop()
    except Exception as e:
        logging.error(f"Failed to start battery monitor: {e}")
        # Ensure GPIO is cleaned up even if startup fails
        try:
            GPIO.cleanup()
        except:
            pass

if __name__ == "__main__":
    main()
