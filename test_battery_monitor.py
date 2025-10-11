#!/usr/bin/env python3
"""
Test script for battery monitor system
Simulates voltage readings to test relay control logic
"""

import RPi.GPIO as GPIO
import time
import logging

# Configuration
RELAY_PIN = 17
VOLTAGE_THRESHOLD_HIGH = 24.8
VOLTAGE_THRESHOLD_LOW = 24.5

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class BatteryMonitorTest:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RELAY_PIN, GPIO.OUT)
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Start with charger connected
        self.charger_connected = True
        
    def control_charger(self, disconnect=False):
        """Control charger connection via relay"""
        if disconnect and self.charger_connected:
            GPIO.output(RELAY_PIN, GPIO.HIGH)
            self.charger_connected = False
            logging.info("? CHARGER DISCONNECTED - Voltage too high!")
            
        elif not disconnect and not self.charger_connected:
            GPIO.output(RELAY_PIN, GPIO.LOW)
            self.charger_connected = True
            logging.info("? Charger reconnected - Voltage safe")
            
    def test_voltage_scenarios(self):
        """Test different voltage scenarios"""
        test_voltages = [
            (24.0, "Normal charging voltage"),
            (24.5, "At low threshold"),
            (24.7, "Approaching high threshold"),
            (24.9, "Above high threshold - should disconnect"),
            (25.1, "Dangerously high - should stay disconnected"),
            (24.6, "Dropping but still above low threshold"),
            (24.4, "Below low threshold - should reconnect"),
            (24.2, "Safe charging voltage")
        ]
        
        logging.info("Starting battery monitor test...")
        logging.info(f"High threshold: {VOLTAGE_THRESHOLD_HIGH}V")
        logging.info(f"Low threshold: {VOLTAGE_THRESHOLD_LOW}V")
        
        for voltage, description in test_voltages:
            logging.info(f"\n--- Testing: {voltage}V ({description}) ---")
            
            # Apply safety logic
            if voltage >= VOLTAGE_THRESHOLD_HIGH:
                self.control_charger(disconnect=True)
            elif voltage <= VOLTAGE_THRESHOLD_LOW:
                self.control_charger(disconnect=False)
                
            status = "DISCONNECTED" if not self.charger_connected else "Connected"
            logging.info(f"Voltage: {voltage}V - Charger: {status}")
            
            time.sleep(2)  # Pause between tests
            
    def cleanup(self):
        """Clean up GPIO"""
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure charger is connected
        GPIO.cleanup()
        logging.info("Test completed - Charger connected")

def main():
    try:
        test = BatteryMonitorTest()
        test.test_voltage_scenarios()
    except KeyboardInterrupt:
        logging.info("Test interrupted by user")
    except Exception as e:
        logging.error(f"Test error: {e}")
    finally:
        try:
            test.cleanup()
        except:
            GPIO.cleanup()

if __name__ == "__main__":
    main()
