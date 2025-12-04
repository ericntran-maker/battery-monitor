#!/usr/bin/env python3
"""
Smart Battery Monitor with Time-of-Day Optimization
Monitors 6S battery voltage and controls charger relay based on:
1. Safety voltage thresholds
2. Time-of-day electricity costs (optimized for your TOD rates)
3. Solar panel availability detection
"""

import RPi.GPIO as GPIO
import serial
import time
import logging
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time, timedelta
from collections import deque
import os

# Import configuration
from config import *

class SmartBatteryMonitor:
    def __init__(self):
        self.setup_logging()
        self.setup_gpio()
        self.setup_serial()
        
        # State tracking - read actual relay state instead of assuming
        self.charger_connected = self.read_relay_state()
        self.last_voltage = 0.0
        self.voltage_history = deque(maxlen=int(SOLAR_DETECTION_WINDOW / MONITOR_INTERVAL))
        self.last_detailed_log = 0
        self.solar_detected = False
        self.first_decision = True  # Flag to enforce strict thresholds on first decision
        
        # Charger toggle tracking (detect rapid oscillation)
        self.charger_state_changes = deque(maxlen=10)  # Track last 10 state changes with timestamps
        self.last_rapid_toggle_alert = None  # Track when we last sent rapid toggle alert
        
        # Email notification tracking
        self.last_email_alert = None
        self.last_email_critical = None
        self.last_email_recovery = None
        self.last_email_high_voltage = None
        self.last_email_critical_high = None
        self.last_email_comm_failure = None
        self.voltage_alert_sent = False
        self.voltage_critical_sent = False
        self.voltage_high_sent = False
        self.voltage_critical_high_sent = False
        self.comm_failure_sent = False
        
        # Recovery notification flags - prevent multiple recovery emails
        self.recovery_email_sent = False
        
        # Communication failure tracking
        self.last_successful_voltage_read = time.time()
        self.consecutive_read_failures = 0
        
        # Inverter reset tracking
        self.last_inverter_reset_date = None
        
        # Charging failure detection tracking
        self.ev_charging_start_time = None
        self.ev_charging_start_voltage = None
        self.last_charging_failure_alert = None
        
        # Internet connectivity health check tracking
        self.last_internet_check = 0
        self.consecutive_internet_failures = 0
        self.last_internet_failure_alert = None
        
        # Voltage stall detection tracking
        self.voltage_stall_start_time = None
        self.voltage_stall_start_voltage = None
        self.last_voltage_stall_alert = None
        
        # CSV logging setup
        if ENABLE_CSV_LOGGING:
            self.setup_csv_logging()
            
    def setup_logging(self):
        """Initialize logging system"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler()
            ]
        )
        
    def setup_csv_logging(self):
        """Setup CSV logging for voltage history"""
        if not os.path.exists(VOLTAGE_LOG_FILE):
            with open(VOLTAGE_LOG_FILE, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    'timestamp', 'voltage', 'charger_connected', 'solar_detected',
                    'in_preferred_hours', 'in_avoid_hours', 'charging_decision',
                    'rate_type', 'current_rate_cents', 'has_ev_credit', 'utility_season', 
                    'monthly_season', 'solar_factor', 'is_weekend'
                ])
                
    def log_to_csv(self, voltage, charging_decision):
        """Log data to CSV file with rate information"""
        if not ENABLE_CSV_LOGGING:
            return
            
        try:
            rate_type, current_rate, has_ev_credit = self.get_current_rate_info()
            
            with open(VOLTAGE_LOG_FILE, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    datetime.now().isoformat(),
                    f"{voltage:.3f}",
                    self.charger_connected,
                    self.solar_detected,
                    self.is_preferred_charging_time(),
                    self.is_avoid_charging_time(),
                    charging_decision,
                    rate_type,
                    f"{current_rate:.2f}",
                    has_ev_credit,
                    self.get_current_season(),  # Utility season for rates
                    self.get_monthly_season_name(),  # Descriptive monthly season
                    f"{self.get_solar_factor():.2f}",  # Solar generation factor
                    self.is_weekend_or_holiday()
                ])
        except Exception as e:
            logging.error(f"Failed to write to CSV: {e}")
            
    def setup_gpio(self):
        """Initialize GPIO for relay control"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)  # Initialize as output, default to connected
        GPIO.setup(INVERTER_PIN, GPIO.OUT, initial=GPIO.LOW)  # Initialize inverter pin, default to ON
        logging.info("GPIO initialized (relay and inverter)")
    
    def read_relay_state(self):
        """Read the current relay state to determine if charger is connected"""
        try:
            # GPIO.LOW = relay off = charger connected (normally closed relay)
            # GPIO.HIGH = relay on = charger disconnected
            state = GPIO.input(RELAY_PIN)
            is_connected = (state == GPIO.LOW)
            logging.info(f"Initial charger state detected: {'Connected' if is_connected else 'Disconnected'} (GPIO: {state})")
            return is_connected
        except Exception as e:
            logging.warning(f"Could not read relay state, defaulting to connected: {e}")
            return True  # Safe default
        
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
            self.serial_port = self.find_usb_device()
            self.ser = serial.Serial(self.serial_port, baudrate=BAUD_RATE, timeout=2)
            logging.info(f"Serial connection established on {self.serial_port}")
        except Exception as e:
            logging.error(f"Failed to setup serial connection: {e}")
            raise
            
    def read_voltage(self, recovery_attempt=False):
        """Read voltage from VE.Direct protocol"""
        try:
            self.ser.flushInput()
            
            # Try more attempts since VE.Direct sends continuous data
            for attempt in range(50):  # Increased from 10 to 50
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                
                # Skip empty lines and null characters
                if not line or line == '\x00' or len(line) < 2:
                    continue
                    
                if line.startswith("V"):
                    try:
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            mv = int(parts[1])
                            voltage = mv / 1000.0
                            self.last_voltage = voltage
                            
                            # Track successful read
                            self.last_successful_voltage_read = time.time()
                            self.consecutive_read_failures = 0
                            
                            # Add to history for solar detection
                            self.voltage_history.append((time.time(), voltage))
                            
                            return voltage
                    except (ValueError, IndexError) as e:
                        logging.warning(f"Error parsing voltage line '{line}': {e}")
                        continue
                        
            logging.warning("No voltage reading received after 50 attempts")
            self.consecutive_read_failures += 1
            return None
            
        except Exception as e:
            logging.error(f"Error reading voltage: {e}")
            
            # Try to recover from USB device errors (only on first attempt)
            if not recovery_attempt and ("Input/output error" in str(e) or "device reports readiness" in str(e)):
                logging.warning("USB I/O error detected - attempting to reconnect...")
                try:
                    self.ser.close()
                except:
                    pass
                
                try:
                    # Try to find and reconnect to USB device
                    new_port = self.find_usb_device()
                    if new_port != self.serial_port:
                        logging.info(f"USB device changed from {self.serial_port} to {new_port}")
                        self.serial_port = new_port
                    
                    self.ser = serial.Serial(self.serial_port, baudrate=BAUD_RATE, timeout=2)
                    logging.info(f"Successfully reconnected to {self.serial_port}")
                    
                    # Try reading voltage again after reconnection (mark as recovery attempt)
                    return self.read_voltage(recovery_attempt=True)
                    
                except Exception as reconnect_error:
                    logging.error(f"Failed to reconnect USB device: {reconnect_error}")
            
            # Track failure
            self.consecutive_read_failures += 1
            return None
            
    def detect_solar_charging(self):
        """Enhanced solar detection using multiple methods"""
        if not SOLAR_DETECTION_ENABLED:
            return False
        
        # If we don't have enough voltage history yet, use time-based detection as fallback
        if len(self.voltage_history) < 5:
            time_result = self._detect_solar_by_time()
            if time_result:
                self.solar_detected = time_result
            return time_result
            
        try:
            solar_indicators = []
            detection_reasons = []
            
            # Method 1: Voltage Trend Analysis (original method)
            if SOLAR_DETECTION_METHODS.get('voltage_trend', True):
                trend_result = self._detect_solar_by_voltage_trend()
                solar_indicators.append(trend_result)
                if trend_result:
                    detection_reasons.append("voltage_trend")
            
            # Method 2: Time-based Detection (daylight hours)
            if SOLAR_DETECTION_METHODS.get('time_based', True):
                time_result = self._detect_solar_by_time()
                solar_indicators.append(time_result)
                if time_result:
                    detection_reasons.append("daylight_hours")
            
            # Method 3: Voltage Plateau Detection (high voltage sustained)
            if SOLAR_DETECTION_METHODS.get('voltage_plateau', True):
                plateau_result = self._detect_solar_by_plateau()
                solar_indicators.append(plateau_result)
                if plateau_result:
                    detection_reasons.append("voltage_plateau")
            
            # Method 4: Load-Compensated Detection
            if SOLAR_DETECTION_METHODS.get('load_compensation', True):
                load_result = self._detect_solar_with_load_compensation()
                solar_indicators.append(load_result)
                if load_result:
                    detection_reasons.append("load_compensated")
            
            # Solar is active if ANY method detects it (OR logic)
            solar_active = any(solar_indicators)
            
            # Log status changes with detection method
            if solar_active != self.solar_detected:
                reason_str = "+".join(detection_reasons) if detection_reasons else "none"
                logging.info(f"Solar status changed: {'ACTIVE' if solar_active else 'INACTIVE'} "
                           f"(methods: {reason_str}, voltage: {self.last_voltage:.2f}V)")
            
            self.solar_detected = solar_active
            return solar_active
                
        except Exception as e:
            logging.error(f"Solar detection error: {e}")
            
        return False
        
    def _detect_solar_by_voltage_trend(self):
        """Detect solar by rising voltage trend during daylight hours"""
        recent_readings = list(self.voltage_history)[-10:]
        if len(recent_readings) < 5:
            return False
            
        times = [reading[0] for reading in recent_readings]
        voltages = [reading[1] for reading in recent_readings]
        
        time_diff = times[-1] - times[0]
        voltage_diff = voltages[-1] - voltages[0]
        
        if time_diff > 0:
            voltage_rate = voltage_diff / (time_diff / 3600)
            is_daylight = self._detect_solar_by_time()
            
            # Solar detected if voltage is rising during daylight hours
            # (regardless of absolute voltage level)
            return (voltage_rate > SOLAR_VOLTAGE_INCREASE_RATE and is_daylight)
        return False
        
    def _detect_solar_by_time(self):
        """Time-based solar detection using monthly daylight hours"""
        now = datetime.now()
        current_hour = now.hour
        
        # Get precise daylight hours for current month
        start_hour, end_hour = self.get_monthly_daylight_hours()
        is_daylight = start_hour <= current_hour < end_hour
        
        # Apply solar factor for more accurate detection
        solar_factor = self.get_solar_factor()
        
        # In very low solar months (Dec/Jan), be more conservative
        if solar_factor < 0.3:
            # Require more restrictive daylight hours in deep winter
            peak_hours = (start_hour + 2, end_hour - 2)
            if peak_hours[0] < peak_hours[1]:  # Valid range
                is_peak_daylight = peak_hours[0] <= current_hour < peak_hours[1]
                return is_daylight and is_peak_daylight
        
        return is_daylight
        
    def _detect_solar_by_plateau(self):
        """Detect solar by sustained high voltage (even with load)"""
        if self.last_voltage < SOLAR_PLATEAU_THRESHOLD:
            return False
            
        # Check if voltage has been high for minimum duration
        recent_readings = list(self.voltage_history)
        plateau_readings = [r for r in recent_readings 
                          if r[1] >= SOLAR_PLATEAU_THRESHOLD]
        
        if len(plateau_readings) < 2:
            return False
            
        # Check duration of plateau
        plateau_duration = plateau_readings[-1][0] - plateau_readings[0][0]
        is_daylight = self._detect_solar_by_time()
        
        return (plateau_duration >= SOLAR_PLATEAU_MIN_DURATION and 
                is_daylight)
        
    def _detect_solar_with_load_compensation(self):
        """Enhanced load-compensated solar detection using system specs"""
        if len(self.voltage_history) < 20:  # Need more history
            return False
            
        recent_readings = list(self.voltage_history)[-20:]  # Last 10 minutes
        times = [r[0] for r in recent_readings]
        voltages = [r[1] for r in recent_readings]
        
        time_diff = times[-1] - times[0]
        voltage_diff = voltages[-1] - voltages[0]
        
        if time_diff > 0:
            voltage_rate = voltage_diff / (time_diff / 3600)  # V/hour
            is_daylight = self._detect_solar_by_time()
            
            if not is_daylight:
                return False
                
            # Determine expected voltage drop based on system load patterns
            # With 18kWh battery and up to 1kW load, we can estimate behavior
            
            # Strong solar indication: voltage rising despite potential load
            if voltage_rate > 0.05:  # Rising faster than 0.05V/hour
                return True
                
            # Moderate solar indication: voltage stable or dropping slowly
            # Expected drops: Light load: -0.03V/h, Typical: -0.08V/h, Heavy: -0.15V/h
            
            if self.last_voltage > SOLAR_STRONG_GENERATION_THRESHOLD:
                # High voltage suggests strong solar - even slow drop indicates solar
                expected_drop_with_solar = -LIGHT_LOAD_VOLTAGE_DROP  # Solar compensating
                return voltage_rate > expected_drop_with_solar
                
            elif self.last_voltage > SOLAR_PLATEAU_THRESHOLD:
                # Medium voltage - compare to typical load drop
                expected_drop_with_solar = -TYPICAL_NIGHTTIME_VOLTAGE_DROP * 0.5  # Solar partially compensating
                return voltage_rate > expected_drop_with_solar
                
            else:
                # Lower voltage - need clear indication of solar compensation
                expected_drop_without_solar = -TYPICAL_NIGHTTIME_VOLTAGE_DROP
                # If dropping significantly slower than expected, solar likely active
                return voltage_rate > (expected_drop_without_solar * 0.6)
        
        return False
        
    def _estimate_current_load_level(self):
        """Estimate current system load based on voltage drop rate"""
        if len(self.voltage_history) < 10:
            return "unknown"
            
        recent_readings = list(self.voltage_history)[-10:]
        times = [r[0] for r in recent_readings]
        voltages = [r[1] for r in recent_readings]
        
        time_diff = times[-1] - times[0]
        voltage_diff = voltages[-1] - voltages[0]
        
        if time_diff > 0:
            voltage_rate = voltage_diff / (time_diff / 3600)
            
            # During non-solar hours, voltage drop rate indicates load
            if not self._detect_solar_by_time():
                if voltage_rate <= -HEAVY_LOAD_VOLTAGE_DROP:
                    return "heavy"  # >1kW load
                elif voltage_rate <= -TYPICAL_NIGHTTIME_VOLTAGE_DROP:
                    return "typical"  # ~1kW load
                elif voltage_rate <= -LIGHT_LOAD_VOLTAGE_DROP:
                    return "light"  # <0.5kW load
                else:
                    return "minimal"  # Very light load
                    
        return "unknown"
        
    def is_weekend_or_holiday(self):
        """Check if current day is weekend (rates are different)"""
        return datetime.now().weekday() >= 5  # Saturday = 5, Sunday = 6
        
    def get_current_season(self):
        """Determine if we're in summer or winter rate period (for utility billing)"""
        current_month = datetime.now().month
        if 6 <= current_month <= 9:  # June-September
            return 'summer'
        else:  # October-May
            return 'winter'
    
    def get_current_month_profile(self):
        """Get detailed monthly solar profile for current month"""
        current_month = datetime.now().month
        return MONTHLY_SOLAR_PROFILE.get(current_month, MONTHLY_SOLAR_PROFILE[1])
    
    def get_monthly_season_name(self):
        """Get descriptive seasonal name based on current month"""
        return self.get_current_month_profile()['name']
    
    def get_solar_factor(self):
        """Get solar generation factor for current month (0.0 to 1.0)"""
        return self.get_current_month_profile()['solar_factor']
    
    def get_monthly_daylight_hours(self):
        """Get daylight hours for current month"""
        return self.get_current_month_profile()['daylight']
            
    def get_current_rate_info(self):
        """Get current electricity rate information based on your TOD schedule"""
        now = datetime.now()
        current_hour = now.hour
        is_weekend = self.is_weekend_or_holiday()
        season = self.get_current_season()
        
        # EV credit applies midnight-6AM every day
        has_ev_credit = 0 <= current_hour < 6
        
        if is_weekend:
            # Weekends and holidays are all off-peak
            rate_type = "off_peak_weekend"
            rate = RATE_INFO[season]['off_peak']
        else:
            # Weekday rates based on your TOD schedule
            if season == 'summer':
                if 0 <= current_hour < 12:  # Midnight-noon
                    rate_type = "off_peak"
                    rate = RATE_INFO[season]['off_peak']
                elif 12 <= current_hour < 17:  # Noon-5PM
                    rate_type = "mid_peak"
                    rate = RATE_INFO[season]['mid_peak']
                elif 17 <= current_hour < 20:  # 5PM-8PM (PEAK - most expensive!)
                    rate_type = "peak"
                    rate = RATE_INFO[season]['peak']
                else:  # 8PM-midnight
                    rate_type = "off_peak"
                    rate = RATE_INFO[season]['off_peak']
            else:  # winter
                if 17 <= current_hour < 20:  # 5PM-8PM (PEAK)
                    rate_type = "peak"
                    rate = RATE_INFO[season]['peak']
                else:  # All other hours are off-peak in winter
                    rate_type = "off_peak"
                    rate = RATE_INFO[season]['off_peak']
        
        # Apply EV credit if applicable (negative cost!)
        if has_ev_credit:
            rate += RATE_INFO[season]['ev_credit']  # EV credit is negative
            rate_type += "_with_ev_credit"
            
        return rate_type, rate, has_ev_credit
        
    def is_preferred_charging_time(self):
        """Check if current time is in preferred charging hours"""
        current_hour = datetime.now().hour
        is_weekend = self.is_weekend_or_holiday()
        
        # Weekends have off-peak rates all day, but still use strategic timing
        # Only treat EV credit hours as truly "preferred" on weekends
        if is_weekend:
            # EV credit hours are preferred even on weekends (cheapest rates)
            if 0 <= current_hour < 6:
                return True
            # Other weekend hours are "acceptable" but not "preferred"
            return False
            
        # Check preferred hours for weekdays
        for start_hour, end_hour in PREFERRED_CHARGING_HOURS:
            if start_hour <= end_hour:
                # Same day range
                if start_hour <= current_hour < end_hour:
                    return True
            else:
                # Overnight range (crosses midnight)
                if current_hour >= start_hour or current_hour < end_hour:
                    return True
                    
        return False
        
    def is_avoid_charging_time(self):
        """Check if current time is in avoid charging hours (peak rates)"""
        current_hour = datetime.now().hour
        is_weekend = self.is_weekend_or_holiday()
        
        # Weekends never have peak rates
        if is_weekend:
            return False
            
        # Check avoid hours for weekdays only (5PM-8PM peak rates)
        for start_hour, end_hour in AVOID_CHARGING_HOURS:
            if start_hour <= end_hour:
                if start_hour <= current_hour < end_hour:
                    return True
            else:
                if current_hour >= start_hour or current_hour < end_hour:
                    return True
                    
        return False
    
    def is_camping_period(self):
        """Check if current date falls within any camping period"""
        from datetime import datetime, date
        
        if not CAMPING_PERIODS:
            return False, None
            
        today = date.today()
        
        for period in CAMPING_PERIODS:
            if len(period) == 3:
                start_str, end_str, voltage_threshold = period
            else:
                # Handle case where voltage threshold is not specified
                start_str, end_str = period[:2]
                voltage_threshold = DEFAULT_CAMPING_VOLTAGE
            
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                
                if start_date <= today <= end_date:
                    return True, voltage_threshold
            except ValueError as e:
                logging.warning(f"Invalid camping period date format: {period} - {e}")
                continue
        
        return False, None
    
    def schedule_reboot(self):
        """Schedule a system reboot to prevent lockups"""
        import subprocess
        import sys
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"🔄 SCHEDULED REBOOT: Daily maintenance reboot at {current_time}")
        logging.info("💾 Saving final status before reboot...")
        
        # Log final system state
        voltage = self.read_voltage()
        if voltage:
            logging.info(f"📊 Final voltage reading: {voltage:.2f}V")
            logging.info(f"🔌 Final charger state: {'Connected' if self.charger_connected else 'Disconnected'}")
        
        # Schedule reboot immediately (now instead of +1 minute)
        try:
            logging.info("⏰ Executing system reboot NOW...")
            # Flush all logs before reboot
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Execute reboot immediately
            subprocess.run(['sudo', 'reboot'], check=False)
            
            # If we get here, reboot command was issued - exit the script
            logging.info("✅ Reboot command issued, exiting script...")
            sys.exit(0)
            
        except Exception as e:
            logging.error(f"❌ Failed to execute reboot: {e}")
            # Continue running if reboot fails
            return
    
    def reset_inverter_if_needed(self):
        """Reset inverter once per day at scheduled time to prevent failures"""
        if not INVERTER_RESET_ENABLED:
            return
        
        now = datetime.now()
        current_date = now.date()
        
        # Check if we're in the reset time window and haven't reset today
        if (now.hour == INVERTER_RESET_HOUR and 
            now.minute >= INVERTER_RESET_MINUTE and 
            now.minute < INVERTER_RESET_MINUTE + 5 and
            self.last_inverter_reset_date != current_date):
            
            current_time = now.strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"🔄 INVERTER RESET: Daily maintenance reset at {current_time}")
            
            try:
                # Turn inverter OFF (GPIO.HIGH)
                logging.info(f"⚡ Turning inverter OFF for {INVERTER_RESET_DURATION} seconds...")
                GPIO.output(INVERTER_PIN, GPIO.HIGH)
                time.sleep(INVERTER_RESET_DURATION)
                
                # Turn inverter back ON (GPIO.LOW)
                GPIO.output(INVERTER_PIN, GPIO.LOW)
                logging.info("✅ Inverter reset complete - inverter is now ON")
                
                # Mark that we've reset today
                self.last_inverter_reset_date = current_date
                
            except Exception as e:
                logging.error(f"❌ Failed to reset inverter: {e}")
                # Ensure inverter is back ON even if error occurred
                try:
                    GPIO.output(INVERTER_PIN, GPIO.LOW)
                except:
                    pass
    
    def check_charging_failure(self, voltage):
        """Detect if charger is connected but not actually charging during EV credit hours"""
        if not CHARGING_FAILURE_DETECTION_ENABLED:
            return
        
        now = datetime.now()
        current_hour = now.hour
        
        # Only check during EV credit hours (midnight-6AM)
        if not (0 <= current_hour < 6):
            # Reset tracking when outside EV hours
            self.ev_charging_start_time = None
            self.ev_charging_start_voltage = None
            return
        
        # Only check if voltage is below threshold (not already full)
        if voltage >= CHARGING_FAILURE_MAX_VOLTAGE:
            self.ev_charging_start_time = None
            self.ev_charging_start_voltage = None
            return
        
        # Only check if charger is supposed to be connected
        if not self.charger_connected:
            self.ev_charging_start_time = None
            self.ev_charging_start_voltage = None
            return
        
        # Start tracking if this is the first check during charging
        if self.ev_charging_start_time is None:
            self.ev_charging_start_time = time.time()
            self.ev_charging_start_voltage = voltage
            logging.info(f"🔋 Started tracking EV charging: {voltage:.2f}V at {now.strftime('%H:%M')}")
            return
        
        # Check if enough time has passed
        elapsed_minutes = (time.time() - self.ev_charging_start_time) / 60
        if elapsed_minutes < CHARGING_FAILURE_CHECK_MINUTES:
            return
        
        # Calculate voltage increase
        voltage_increase = voltage - self.ev_charging_start_voltage
        
        # Check if voltage increased enough
        if voltage_increase < CHARGING_FAILURE_MIN_VOLTAGE_INCREASE:
            # Charging failure detected!
            cooldown_period = timedelta(hours=1)
            
            # Only alert once per hour to avoid spam
            if (self.last_charging_failure_alert is None or 
                now - self.last_charging_failure_alert > cooldown_period):
                
                logging.warning(f"⚠️ CHARGING FAILURE DETECTED!")
                logging.warning(f"   Start: {self.ev_charging_start_voltage:.2f}V at {datetime.fromtimestamp(self.ev_charging_start_time).strftime('%H:%M')}")
                logging.warning(f"   Now:   {voltage:.2f}V at {now.strftime('%H:%M')}")
                logging.warning(f"   Increase: {voltage_increase:.2f}V over {elapsed_minutes:.0f} minutes")
                logging.warning(f"   Expected: >{CHARGING_FAILURE_MIN_VOLTAGE_INCREASE}V")
                
                # Send email alert
                subject = f"⚠️ CHARGING FAILURE: Battery not charging during EV credit hours!"
                message = f"""
CHARGING FAILURE DETECTED!

Your battery charger appears to be connected but NOT actually charging during the EV credit period (midnight-6AM).

Charging Session Details:
- Started: {datetime.fromtimestamp(self.ev_charging_start_time).strftime('%Y-%m-%d %H:%M:%S')}
- Duration: {elapsed_minutes:.0f} minutes
- Starting Voltage: {self.ev_charging_start_voltage:.2f}V
- Current Voltage: {voltage:.2f}V
- Voltage Increase: {voltage_increase:.2f}V
- Expected Increase: >{CHARGING_FAILURE_MIN_VOLTAGE_INCREASE}V

Current Status:
- Charger Relay: {'Connected' if self.charger_connected else 'Disconnected'}
- Time: {now.strftime('%H:%M')} (EV credit hours: midnight-6AM)
- Solar: {'Active' if self.solar_detected else 'Inactive'}

AUTOMATIC ACTIONS TAKEN:
1. Performing inverter reset to attempt recovery
2. This alert will not repeat for 1 hour

Possible Causes:
- Charger not plugged in or turned on
- Charger malfunction or tripped breaker
- Loose connection or bad cable
- Shore power issue

Recommended Actions:
- Check if charger is physically connected and powered
- Verify shore power is available
- Check charger status lights/indicators
- Inspect connections and cables
- Consider manual charger reset

This is valuable EV credit time being wasted - please investigate immediately!
                """
                
                self.send_email_notification(subject, message, is_critical=True)
                self.last_charging_failure_alert = now
                
                # Attempt recovery by resetting inverter
                logging.info("🔄 Attempting recovery: Resetting inverter...")
                try:
                    GPIO.output(INVERTER_PIN, GPIO.HIGH)
                    time.sleep(INVERTER_RESET_DURATION)
                    GPIO.output(INVERTER_PIN, GPIO.LOW)
                    logging.info("✅ Inverter reset complete")
                except Exception as e:
                    logging.error(f"❌ Inverter reset failed: {e}")
            
            # Reset tracking to check again in next cycle
            self.ev_charging_start_time = None
            self.ev_charging_start_voltage = None
        else:
            # Charging is working - log success and reset tracking for next check
            logging.info(f"✅ EV charging verified: {voltage_increase:.2f}V increase over {elapsed_minutes:.0f} minutes")
            self.ev_charging_start_time = None
            self.ev_charging_start_voltage = None
    
    def detect_voltage_stall(self, voltage):
        """Detect if voltage isn't increasing while charger is connected (anytime)"""
        if not VOLTAGE_STALL_DETECTION_ENABLED:
            return
        
        now = datetime.now()
        
        # Only check when charger is connected and voltage is below threshold
        if not self.charger_connected or voltage >= VOLTAGE_STALL_MAX_VOLTAGE:
            # Reset tracking when charger disconnected or battery nearly full
            self.voltage_stall_start_time = None
            self.voltage_stall_start_voltage = None
            return
        
        # Start tracking if this is the first check during charging
        if self.voltage_stall_start_time is None:
            self.voltage_stall_start_time = time.time()
            self.voltage_stall_start_voltage = voltage
            logging.debug(f"📊 Started voltage stall tracking: {voltage:.2f}V")
            return
        
        # Check if enough time has passed
        elapsed_minutes = (time.time() - self.voltage_stall_start_time) / 60
        if elapsed_minutes < VOLTAGE_STALL_CHECK_MINUTES:
            return
        
        # Calculate voltage increase
        voltage_increase = voltage - self.voltage_stall_start_voltage
        
        # Check if voltage increased enough
        if voltage_increase < VOLTAGE_STALL_MIN_INCREASE:
            # Voltage stall detected!
            cooldown_period = timedelta(hours=VOLTAGE_STALL_COOLDOWN_HOURS)
            
            # Only alert once per cooldown period to avoid spam
            if (self.last_voltage_stall_alert is None or 
                now - self.last_voltage_stall_alert > cooldown_period):
                
                logging.warning(f"⚠️ VOLTAGE STALL DETECTED!")
                logging.warning(f"   Start: {self.voltage_stall_start_voltage:.2f}V at {datetime.fromtimestamp(self.voltage_stall_start_time).strftime('%H:%M')}")
                logging.warning(f"   Now:   {voltage:.2f}V at {now.strftime('%H:%M')}")
                logging.warning(f"   Increase: {voltage_increase:.2f}V over {elapsed_minutes:.0f} minutes")
                logging.warning(f"   Expected: >{VOLTAGE_STALL_MIN_INCREASE}V")
                
                # Send email notification (not critical - just informational)
                subject = f"⚠️ Voltage Stall: Battery not charging ({voltage:.2f}V)"
                message = f"""
VOLTAGE STALL DETECTED

Your battery charger is connected but voltage has not increased for {elapsed_minutes:.0f} minutes.

Details:
- Started Tracking: {datetime.fromtimestamp(self.voltage_stall_start_time).strftime('%Y-%m-%d %H:%M:%S')}
- Duration: {elapsed_minutes:.0f} minutes
- Starting Voltage: {self.voltage_stall_start_voltage:.2f}V
- Current Voltage: {voltage:.2f}V
- Voltage Change: {voltage_increase:+.2f}V
- Expected Increase: >{VOLTAGE_STALL_MIN_INCREASE}V

Current Status:
- Charger Relay: Connected
- Time: {now.strftime('%H:%M')}
- Solar: {'Active' if self.solar_detected else 'Inactive'}

Possible Causes:
- Charger not plugged in or turned on
- Charger malfunction or tripped breaker
- Inverter issue (may need reset)
- Shore power issue
- Battery near full (false positive if voltage >{VOLTAGE_STALL_MAX_VOLTAGE}V)

You may want to:
- Check charger connections
- Consider running: python3 test_inverter_reset.py

This notification will not repeat for {VOLTAGE_STALL_COOLDOWN_HOURS} hours.
                """
                
                self.send_email_notification(subject, message, is_critical=False)
                self.last_voltage_stall_alert = now
            
            # Reset tracking to check again in next cycle
            self.voltage_stall_start_time = None
            self.voltage_stall_start_voltage = None
        else:
            # Charging is working - reset tracking for next check
            logging.debug(f"✅ Charging verified: {voltage_increase:.2f}V increase over {elapsed_minutes:.0f} minutes")
            self.voltage_stall_start_time = None
            self.voltage_stall_start_voltage = None
    
    def check_internet_connectivity(self):
        """Check if Pi can communicate with the internet"""
        import socket
        
        for host in INTERNET_CHECK_HOSTS:
            try:
                # Try to connect to the host on port 53 (DNS)
                socket.setdefaulttimeout(INTERNET_CHECK_TIMEOUT)
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, 53))
                return True
            except (socket.error, socket.timeout):
                continue
        
        return False
    
    def check_internet_health(self):
        """Monitor internet connectivity and reset Pi if connection is lost"""
        if not INTERNET_HEALTH_CHECK_ENABLED:
            return
        
        now = time.time()
        
        # Only check at specified intervals
        if now - self.last_internet_check < INTERNET_CHECK_INTERVAL:
            return
        
        self.last_internet_check = now
        
        # Check connectivity
        is_connected = self.check_internet_connectivity()
        
        if is_connected:
            # Connection successful - reset failure counter
            if self.consecutive_internet_failures > 0:
                logging.info(f"✅ Internet connectivity restored after {self.consecutive_internet_failures} failures")
                self.consecutive_internet_failures = 0
                self.last_internet_failure_alert = None
        else:
            # Connection failed
            self.consecutive_internet_failures += 1
            logging.warning(f"⚠️ Internet connectivity check failed ({self.consecutive_internet_failures}/{INTERNET_FAILURE_THRESHOLD})")
            
            # Send alert on first failure
            if self.consecutive_internet_failures == 1:
                current_time = datetime.now()
                cooldown_period = timedelta(hours=1)
                
                # Only alert once per hour to avoid spam
                if (self.last_internet_failure_alert is None or 
                    current_time - self.last_internet_failure_alert > cooldown_period):
                    
                    subject = "⚠️ Internet Connectivity Issue - RV Battery Monitor"
                    message = f"""
Internet Connectivity Warning

Your Raspberry Pi battery monitor is having trouble connecting to the internet.

Status:
- Consecutive failures: {self.consecutive_internet_failures}
- Threshold for reset: {INTERNET_FAILURE_THRESHOLD}
- Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
- Hosts checked: {', '.join(INTERNET_CHECK_HOSTS)}

Action:
- The system will continue monitoring
- If {INTERNET_FAILURE_THRESHOLD} consecutive checks fail, the Pi will automatically reset
- This helps recover from network issues that may prevent remote monitoring

Battery Status:
- Voltage: {self.last_voltage:.2f}V
- Charger: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}

The system is still monitoring battery voltage and controlling the charger normally.
                    """
                    
                    self.send_email_notification(subject, message)
                    self.last_internet_failure_alert = current_time
            
            # Check if we've reached the threshold for reset
            if self.consecutive_internet_failures >= INTERNET_FAILURE_THRESHOLD:
                if INTERNET_RESET_ENABLED:
                    self.reset_pi_for_internet_failure()
                else:
                    logging.error(f"❌ Internet connectivity lost for {INTERNET_FAILURE_THRESHOLD} consecutive checks, but auto-reset is disabled")
    
    def reset_pi_for_internet_failure(self):
        """Reset the Raspberry Pi due to internet connectivity failure"""
        import subprocess
        import sys
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.error(f"🔄 INTERNET CONNECTIVITY FAILURE: Resetting Pi at {current_time}")
        logging.error(f"   Consecutive failures: {self.consecutive_internet_failures}")
        logging.error(f"   Last successful check: {datetime.fromtimestamp(self.last_internet_check - (self.consecutive_internet_failures * INTERNET_CHECK_INTERVAL)).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Log final system state
        voltage = self.last_voltage
        if voltage:
            logging.info(f"📊 Final voltage reading: {voltage:.2f}V")
            logging.info(f"🔌 Final charger state: {'Connected' if self.charger_connected else 'Disconnected'}")
        
        # Try to send email notification before reset
        try:
            subject = "🔄 CRITICAL: Pi Resetting Due to Internet Failure"
            message = f"""
CRITICAL: Raspberry Pi Reset Initiated

Your Raspberry Pi battery monitor has lost internet connectivity and is performing an automatic reset to recover.

Failure Details:
- Consecutive failures: {self.consecutive_internet_failures}
- Last successful check: {datetime.fromtimestamp(self.last_internet_check - (self.consecutive_internet_failures * INTERNET_CHECK_INTERVAL)).strftime('%Y-%m-%d %H:%M:%S')}
- Reset time: {current_time}
- Hosts checked: {', '.join(INTERNET_CHECK_HOSTS)}

Battery Status at Reset:
- Voltage: {voltage:.2f}V
- Charger: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}

The Pi will reboot now and should restore connectivity.
The battery monitoring system will resume automatically after reboot.

If you continue to receive these alerts, there may be a persistent network issue that requires manual intervention.
            """
            
            self.send_email_notification(subject, message, is_critical=True)
        except Exception as e:
            logging.error(f"Failed to send reset notification email: {e}")
        
        # Execute reboot
        try:
            logging.info("⏰ Executing system reboot NOW due to internet failure...")
            # Flush all logs before reboot
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Execute reboot immediately
            subprocess.run(['sudo', 'reboot'], check=False)
            
            # If we get here, reboot command was issued - exit the script
            logging.info("✅ Reboot command issued, exiting script...")
            sys.exit(0)
            
        except Exception as e:
            logging.error(f"❌ Failed to execute reboot: {e}")
            # Reset counter if reboot fails so we can try again later
            self.consecutive_internet_failures = 0
    
    def _camping_mode_logic(self, voltage, threshold):
        """Simple camping logic with hysteresis"""
        # Hysteresis: Disconnect at threshold, reconnect 0.5V below
        if voltage >= threshold:
            return False, f"CAMPING_HIGH_VOLTAGE_{threshold}V"
        elif voltage <= (threshold - 0.5) or not self.charger_connected:
            # Charge if below threshold or if already charging and not too high
            return True, "CAMPING_ALLOW_CHARGING"
        else:
            # In hysteresis band - maintain current state
            if self.charger_connected:
                return True, "CAMPING_ALLOW_CHARGING"
            else:
                return False, f"CAMPING_HYSTERESIS_{threshold}V"
        
    def should_charge(self, voltage):
        """Determine if charging should be enabled based on voltage priority and other factors"""
        
        # Check if we're in a camping period
        is_camping, camping_voltage = self.is_camping_period()
        if is_camping:
            return self._camping_mode_logic(voltage, camping_voltage)
        
        # NORMAL MODE - Full smart charging logic
        # Safety first - always disconnect if voltage too high (ABSOLUTE PRIORITY)
        if voltage >= VOLTAGE_THRESHOLD_HIGH:
            return False, "SAFETY_HIGH_VOLTAGE"
            
        # Hysteresis for high voltage - stay disconnected until voltage drops significantly
        if not self.charger_connected and voltage >= VOLTAGE_THRESHOLD_LOW:
            return False, "SAFETY_HIGH_VOLTAGE_HYSTERESIS"
            
        # CRITICAL: Inverter protection - always charge if approaching cutoff
        if voltage <= CRITICAL_VOLTAGE_THRESHOLD:
            return True, "CRITICAL_INVERTER_PROTECTION"
            
        # Emergency charging - always charge if battery critically low
        if voltage <= EMERGENCY_VOLTAGE_THRESHOLD:
            return True, "EMERGENCY_LOW_VOLTAGE"
        
        # Get current hour for time-based logic
        current_hour = datetime.now().hour
        
        # EV credit hours (12AM-6AM) - always charge (cheapest rates)
        # But stop if voltage gets too high
        if 0 <= current_hour < 6:
            if voltage >= NORMAL_VOLTAGE_THRESHOLD:  # 23.5V - stop if fully charged
                return False, "EV_CREDIT_VOLTAGE_HIGH"
            return True, "EV_CREDIT_PRIORITY"
        
        # Solar is active - prefer charging during solar hours (but respect safety limits)
        # Check this early to avoid conflicts with morning/evening logic
        if self.solar_detected:
            # Stop charging if voltage gets too high, even with solar
            if voltage >= NORMAL_VOLTAGE_THRESHOLD:  # 23.5V
                return False, "SOLAR_VOLTAGE_HIGH"
            return True, "SOLAR_ACTIVE"
        
        # Morning after EV credit (6AM-10AM) - disconnect if voltage is healthy AND no solar
        # This prevents continuing to charge at off-peak rates when voltage is already good
        if 6 <= current_hour < 10:
            # Hysteresis: Start at ≤20.7V, stop at ≥22.0V
            if voltage <= LOW_VOLTAGE_PRIORITY_THRESHOLD:  # 20.7V
                return True, "MORNING_LOW_VOLTAGE_CHARGE"
            elif voltage >= (LOW_VOLTAGE_PRIORITY_THRESHOLD + 1.3):  # 22.0V
                return False, "MORNING_WAIT_FOR_SOLAR"
            else:
                # In hysteresis band (20.7V - 22.0V) - maintain current state
                if self.charger_connected:
                    return True, "MORNING_LOW_VOLTAGE_CHARGE"
                else:
                    return False, "MORNING_WAIT_FOR_SOLAR"
        
        # Evening (8PM-11:59PM) - wait for EV credit unless voltage drops significantly
        # This check must come BEFORE LOW_VOLTAGE_PRIORITY to enforce the wait threshold
        # IMPORTANT: This completely overrides LOW_VOLTAGE_PRIORITY during evening hours
        if 20 <= current_hour <= 23:
            # Start charging: Only if voltage ≤ 20.5V
            # Stop charging: When voltage ≥ 21.5V (1V hysteresis band)
            
            if voltage <= EVENING_EV_WAIT_THRESHOLD:  # 20.5V
                # Voltage is low enough - charge
                return True, "EVENING_LOW_VOLTAGE_CHARGE"
            elif voltage >= (EVENING_EV_WAIT_THRESHOLD + 1.0):  # 21.5V
                # Voltage is high enough - stop charging
                return False, "WAITING_FOR_EV_CREDIT_PERIOD"
            else:
                # Voltage is in the hysteresis band (20.5V - 21.5V)
                # On first decision after startup, enforce strict threshold
                if self.first_decision:
                    return False, "WAITING_FOR_EV_CREDIT_PERIOD"
                # Otherwise, maintain current state to prevent toggling
                if self.charger_connected:
                    return True, "EVENING_LOW_VOLTAGE_CHARGE"
                else:
                    return False, "WAITING_FOR_EV_CREDIT_PERIOD"
            
        # Low voltage priority - prefer charging even during peak hours
        # Hysteresis: Start at ≤20.7V, stop at ≥22.0V
        if voltage <= LOW_VOLTAGE_PRIORITY_THRESHOLD:  # 20.7V
            # Only avoid charging during peak if voltage is not too low AND solar isn't active
            if self.is_avoid_charging_time() and not self.solar_detected:
                # Still charge during peak if voltage is getting concerning
                if voltage <= (LOW_VOLTAGE_PRIORITY_THRESHOLD - 0.2):  # 20.5V
                    return True, "LOW_VOLTAGE_OVERRIDE_PEAK"
                else:
                    return False, "LOW_VOLTAGE_PEAK_AVOIDANCE"
            else:
                return True, "LOW_VOLTAGE_PRIORITY"
        elif voltage >= (LOW_VOLTAGE_PRIORITY_THRESHOLD + 1.3) and self.charger_connected:  # 22.0V
            # Stop charging if voltage is high enough
            # BUT: Don't apply this during preferred hours - let that logic handle it
            if not self.is_preferred_charging_time():
                return False, "LOW_VOLTAGE_CHARGED"
        
        # Daily reboot to prevent system lockups
        # Check if it's the reboot hour (this will trigger once per day during the reboot hour)
        if DAILY_REBOOT_ENABLED and current_hour == DAILY_REBOOT_HOUR and datetime.now().minute < 5:
            # schedule_reboot() will exit the script after issuing reboot command
            # This code will not return if reboot succeeds
            self.schedule_reboot()
            # If we get here, reboot failed - maintain current state
            return self.charger_connected, "REBOOT_FAILED_MAINTAIN_STATE"
        
        # Weekend logic - applies regardless of voltage level (but still safe)
        if self.is_weekend_or_holiday():
            if self.charger_connected:
                # If currently charging, keep charging until voltage gets higher
                if voltage < (LOW_VOLTAGE_PRIORITY_THRESHOLD + 1.0):  # 22.0V - Higher threshold to stop charging
                    return True, "WEEKEND_LOW_VOLTAGE"
                else:
                    return False, "WEEKEND_WAIT_FOR_EV_CREDIT"
            else:
                # If currently not charging, only start if voltage is lower
                if voltage <= (LOW_VOLTAGE_PRIORITY_THRESHOLD + 0.2):  # 21.2V - Lower threshold to start charging
                    return True, "WEEKEND_LOW_VOLTAGE"
                else:
                    return False, "WEEKEND_WAIT_FOR_EV_CREDIT"
        
        # If voltage is healthy (>21.5V), use smart charging logic
        if voltage > EMAIL_RECOVERY_VOLTAGE_THRESHOLD:  # 21.5V
            # Preferred charging hours (now only EV credit on weekends)
            if self.is_preferred_charging_time():
                # Add hysteresis to prevent toggling with LOW_VOLTAGE_CHARGED
                if self.charger_connected:
                    # Keep charging until 23.5V
                    if voltage < NORMAL_VOLTAGE_THRESHOLD:  # 23.5V
                        return True, "PREFERRED_HOURS"
                    else:
                        return False, "VOLTAGE_HIGH_SKIP_PREFERRED"
                else:
                    # Only start charging if voltage dropped below 22.5V
                    if voltage <= (LOW_VOLTAGE_PRIORITY_THRESHOLD + 1.8):  # 22.5V
                        return True, "PREFERRED_HOURS"
                    else:
                        return False, "VOLTAGE_HIGH_SKIP_PREFERRED"
            
            # Daylight hours (potential solar) - charge if voltage reasonable (with hysteresis)
            start_hour, end_hour = self.get_monthly_daylight_hours()
            if start_hour <= current_hour < end_hour:
                if self.charger_connected:
                    # Keep charging until higher voltage
                    if voltage < NORMAL_VOLTAGE_THRESHOLD:  # 23.5V
                        return True, "DAYLIGHT_HOURS_POTENTIAL_SOLAR"
                    else:
                        return False, "VOLTAGE_HIGH_SKIP_DAYLIGHT"
                else:
                    # Start charging at lower voltage
                    if voltage <= VOLTAGE_HEALTHY_THRESHOLD:  # 23.0V
                        return True, "DAYLIGHT_HOURS_POTENTIAL_SOLAR"
                    else:
                        return False, "VOLTAGE_HIGH_SKIP_DAYLIGHT"
            
            # Peak avoidance hours (5PM-8PM) - be conservative
            if self.is_avoid_charging_time():
                return False, "PEAK_RATE_AVOIDANCE"
            
            # Evening (8PM-11:59PM) - wait for EV credit unless voltage drops significantly
            if 20 <= current_hour <= 23:
                if voltage > (LOW_VOLTAGE_PRIORITY_THRESHOLD + 1.2):  # 22.2V - be more willing to wait for EV credit
                    return False, "WAITING_FOR_EV_CREDIT_PERIOD"
            
            # Default for healthy voltage - wait for better rates
            if voltage > VOLTAGE_HEALTHY_THRESHOLD:  # 23.0V - wait for better rates if voltage healthy
                return False, "VOLTAGE_HEALTHY_WAIT_FOR_EV_CREDIT"
        
        # Hysteresis for charger state changes (prevent rapid toggling)
        if self.charger_connected:
            # If currently connected, only disconnect if voltage is high enough
            if voltage > VOLTAGE_THRESHOLD_LOW:  # 23.5V
                return False, "HYSTERESIS_DISCONNECT"
        else:
            # If currently disconnected, only reconnect if voltage dropped significantly
            if voltage > VOLTAGE_THRESHOLD_LOW:
                return False, "HYSTERESIS_STAY_DISCONNECTED"
            
        # Fallback: Check time-based preferences (should rarely reach here)
        if self.is_preferred_charging_time():
            return True, "FALLBACK_PREFERRED_HOURS"
            
        # Default: maintain current state
        return self.charger_connected, "MAINTAIN_STATE"
        
    def get_voltage_status(self, voltage):
        """Get human-readable voltage status (ASCII-only)"""
        if voltage <= CRITICAL_VOLTAGE_THRESHOLD:
            return "CRITICAL"
        elif voltage <= EMERGENCY_VOLTAGE_THRESHOLD:
            return "EMERGENCY"
        elif voltage <= LOW_VOLTAGE_PRIORITY_THRESHOLD:
            return "LOW"
        elif voltage <= NORMAL_VOLTAGE_THRESHOLD:
            return "NORMAL"
        else:
            return "HIGH"
            
    def send_email_notification(self, subject, message, is_critical=False):
        """Send email notification for voltage alerts"""
        if not EMAIL_NOTIFICATIONS_ENABLED:
            return False
            
        if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
            logging.warning("Email notifications enabled but credentials not configured")
            return False
            
        try:
            # Clean all text to ensure ASCII compatibility
            def clean_ascii(text):
                # Replace common unicode characters with ASCII equivalents
                replacements = {
                    '\xa0': ' ',  # Non-breaking space
                    '\u2022': '-',  # Bullet point
                    '\u2013': '-',  # En dash
                    '\u2014': '-',  # Em dash
                    '\u2018': "'",  # Left single quote
                    '\u2019': "'",  # Right single quote
                    '\u201c': '"',  # Left double quote
                    '\u201d': '"',  # Right double quote
                    '🔴': 'CRITICAL',
                    '🟠': 'EMERGENCY', 
                    '🟡': 'LOW',
                    '🟢': 'NORMAL',
                    '🔵': 'HIGH'
                }
                for unicode_char, ascii_char in replacements.items():
                    text = text.replace(unicode_char, ascii_char)
                
                # Remove any remaining non-ASCII characters
                text = ''.join(char if ord(char) < 128 else '?' for char in text)
                return text
            
            # Create message with unique Message-ID to prevent duplicates
            import uuid
            msg = MIMEMultipart()
            msg['From'] = clean_ascii(EMAIL_FROM)
            msg['To'] = clean_ascii(', '.join(EMAIL_TO))
            msg['Subject'] = clean_ascii(subject)
            msg['Message-ID'] = f"<{uuid.uuid4()}@rv-battery-monitor>"
            
            # Add timestamp and system info to message (ASCII-safe)
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            load_level = self._estimate_current_load_level()
            voltage_status = self.get_voltage_status(self.last_voltage)
            voltage_status_clean = clean_ascii(voltage_status)
            
            full_message = f"""
{clean_ascii(message)}

System Status at {current_time}:
- Battery Voltage: {self.last_voltage:.2f}V {voltage_status_clean}
- Charger Status: {'Connected' if self.charger_connected else 'DISCONNECTED'}
- Solar Status: {'Active' if self.solar_detected else 'Inactive'}
- Load Level: {load_level.title()}
- Inverter Cutoff: {INVERTER_CUTOFF_VOLTAGE}V

Battery System: {BATTERY_CAPACITY_KWH}kWh capacity
Typical Load: {TYPICAL_LOAD_KW}kW

This is an automated alert from your RV Battery Monitor.
            """
            
            # Clean the entire message
            full_message_clean = clean_ascii(full_message)
            
            msg.attach(MIMEText(full_message_clean, 'plain'))
            
            # Send email
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            text = msg.as_string()
            
            # Ensure EMAIL_TO is properly handled as a list
            recipients = EMAIL_TO if isinstance(EMAIL_TO, list) else [EMAIL_TO]
            server.sendmail(EMAIL_FROM, recipients, text)
            server.quit()
            
            logging.info(f"Email notification sent: {clean_ascii(subject)}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")
            return False
    
    def test_email_system(self, test_type="basic"):
        """Test email notification system with different scenarios"""
        logging.info(f"🧪 Testing email system: {test_type}")
        
        if not EMAIL_NOTIFICATIONS_ENABLED:
            logging.warning("Email notifications are disabled in config")
            return False
            
        if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
            logging.error("Email configuration incomplete")
            return False
        
        test_scenarios = {
            "basic": (23.5, "🧪 Basic Email Test"),
            "low": (20.9, "🟡 Low Voltage Test"),
            "critical_low": (20.5, "🔴 Critical Low Voltage Test"),
            "high": (24.7, "🟠 High Voltage Test"),
            "critical_high": (25.2, "🔴 Critical High Voltage Test"),
            "recovery": (21.8, "🔵 Recovery Test")
        }
        
        if test_type == "basic":
            # Send a basic test email
            subject = "🧪 Battery Monitor Email Test"
            message = f"""
This is a test email from your RV Battery Monitor system.

Test Details:
- Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- System status: Operational
- Email configuration: Working ✅

Voltage Thresholds:
- Critical high: {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V
- High: {VOLTAGE_THRESHOLD_HIGH}V
- Low: {VOLTAGE_THRESHOLD_LOW}V
- Critical low: {EMAIL_CRITICAL_VOLTAGE_THRESHOLD}V

If you receive this email, your battery monitoring alerts are configured correctly!
            """
            
            success = self.send_email_notification(subject, message)
            if success:
                logging.info("✅ Test email sent successfully")
            else:
                logging.error("❌ Test email failed")
            return success
            
        elif test_type in test_scenarios:
            voltage, description = test_scenarios[test_type]
            logging.info(f"Testing {description} at {voltage}V")
            
            # Temporarily store current state
            original_voltage = self.last_voltage
            self.last_voltage = voltage
            
            # Trigger the alert
            self.check_voltage_alerts(voltage)
            
            # Restore original state
            self.last_voltage = original_voltage
            
            logging.info(f"✅ {description} completed")
            return True
            
        else:
            logging.error(f"Unknown test type: {test_type}")
            return False
            
    def check_voltage_alerts(self, voltage):
        """Check voltage and send email alerts if needed"""
        if not EMAIL_NOTIFICATIONS_ENABLED:
            return
            
        now = datetime.now()
        cooldown_period = timedelta(minutes=EMAIL_COOLDOWN_MINUTES)
        
        # Critical HIGH voltage alert (most urgent - potential damage)
        if voltage >= EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD:
            if not self.voltage_critical_high_sent or (
                self.last_email_critical_high and now - self.last_email_critical_high > cooldown_period
            ):
                subject = f"CRITICAL HIGH VOLTAGE ALERT: RV Battery at {voltage:.2f}V - IMMEDIATE ATTENTION REQUIRED!"
                message = f"""
CRITICAL HIGH VOLTAGE ALERT!

Your RV battery voltage has reached {voltage:.2f}V, which is DANGEROUSLY HIGH and exceeds the critical threshold of {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V.

IMMEDIATE ACTIONS REQUIRED:
- Charger has been automatically DISCONNECTED for safety
- Check solar charge controller settings - may be overcharging
- Verify battery condition - possible cell imbalance or failure
- Consider disconnecting solar panels if voltage continues rising
- Monitor voltage closely - do not leave unattended

POTENTIAL RISKS:
- Battery damage or reduced lifespan
- Electrolyte loss (venting)
- Fire or explosion risk in extreme cases
- System component damage

Current Status:
- Charger: {'Connected' if self.charger_connected else 'DISCONNECTED (SAFETY)'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}
- Critical high threshold: {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V
- Normal high threshold: {VOLTAGE_THRESHOLD_HIGH}V

This voltage level requires immediate investigation and corrective action.
                """
                
                if self.send_email_notification(subject, message, is_critical=True):
                    self.last_email_critical_high = now
                    self.voltage_critical_high_sent = True
                    self.recovery_email_sent = False  # Reset recovery flag for new alert
                    
        # Critical LOW voltage alert (most urgent)
        if voltage <= EMAIL_CRITICAL_VOLTAGE_THRESHOLD:
            if not self.voltage_critical_sent or (
                self.last_email_critical and now - self.last_email_critical > cooldown_period
            ):
                subject = f"CRITICAL ALERT: RV Battery at {voltage:.2f}V - Immediate Action Required!"
                message = f"""
CRITICAL BATTERY ALERT!

Your RV battery voltage has dropped to {voltage:.2f}V, which is dangerously close to your inverter cutoff voltage of {INVERTER_CUTOFF_VOLTAGE}V.

IMMEDIATE ACTION REQUIRED:
- Check if charger is connected and working
- Reduce power consumption immediately
- Consider starting generator if available
- System may shut down soon if voltage continues to drop

Time until inverter shutdown: Approximately {((voltage - INVERTER_CUTOFF_VOLTAGE) / HEAVY_LOAD_VOLTAGE_DROP * 60):.0f} minutes at current load.
                """
                
                if self.send_email_notification(subject, message, is_critical=True):
                    self.last_email_critical = now
                    self.voltage_critical_sent = True
                    self.recovery_email_sent = False  # Reset recovery flag for new alert
                    
        # Regular low voltage alert (only if not already critical)
        elif voltage <= EMAIL_ALERT_VOLTAGE_THRESHOLD and voltage > EMAIL_CRITICAL_VOLTAGE_THRESHOLD:
            if not self.voltage_alert_sent or (
                self.last_email_alert and now - self.last_email_alert > cooldown_period
            ):
                subject = f"Low Battery Alert: RV Battery at {voltage:.2f}V"
                message = f"""
Low Battery Voltage Alert

Your RV battery voltage has dropped to {voltage:.2f}V.

Current Status:
- Charger: {'Connected' if self.charger_connected else 'DISCONNECTED'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}
- Critical threshold: {EMAIL_CRITICAL_VOLTAGE_THRESHOLD}V
- Inverter cutoff: {INVERTER_CUTOFF_VOLTAGE}V

Recommended Actions:
- Ensure charger is connected if available
- Consider reducing power consumption
- Monitor voltage closely
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_alert = now
                    self.voltage_alert_sent = True
                    self.recovery_email_sent = False  # Reset recovery flag for new alert

        # High voltage alert (safety threshold reached)
        elif voltage >= VOLTAGE_THRESHOLD_HIGH:
            if not self.voltage_high_sent or (
                self.last_email_high_voltage and now - self.last_email_high_voltage > cooldown_period
            ):
                subject = f"HIGH VOLTAGE ALERT: RV Battery at {voltage:.2f}V - Charger Disconnected!"
                message = f"""
HIGH VOLTAGE SAFETY ALERT!

Your RV battery voltage has reached {voltage:.2f}V, which exceeds the safety threshold of {VOLTAGE_THRESHOLD_HIGH}V.

SAFETY ACTION TAKEN:
- Charger has been automatically DISCONNECTED to prevent overcharging
- System will reconnect charger when voltage drops below {VOLTAGE_THRESHOLD_LOW}V

Current Status:
- Charger: {'Connected' if self.charger_connected else 'DISCONNECTED (SAFETY)'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}
- Safety disconnect threshold: {VOLTAGE_THRESHOLD_HIGH}V
- Reconnect threshold: {VOLTAGE_THRESHOLD_LOW}V

This is normal behavior when:
- Solar panels are generating power and battery is full
- External charger is providing too much current
- Battery is reaching full charge capacity

No immediate action required - system is operating safely.
Monitor voltage and ensure it stabilizes below {VOLTAGE_THRESHOLD_HIGH}V.
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_high_voltage = now
                    self.voltage_high_sent = True
                    self.recovery_email_sent = False  # Reset recovery flag for new alert
                    
        # Recovery notification (for both low and high voltage alerts)
        elif EMAIL_RECOVERY_VOLTAGE_THRESHOLD <= voltage < VOLTAGE_THRESHOLD_HIGH:
            # Recovery from low voltage alerts - SEND ONLY ONCE
            if (self.voltage_alert_sent or self.voltage_critical_sent) and not self.recovery_email_sent:
                subject = f"Battery Recovery: RV Battery at {voltage:.2f}V"
                message = f"""
Battery Voltage Recovery

Your RV battery voltage has recovered to {voltage:.2f}V.

The low voltage alert condition has been cleared.
System is operating normally.
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_recovery = now
                    # Reset alert flags and mark recovery as sent
                    self.voltage_alert_sent = False
                    self.voltage_critical_sent = False
                    self.recovery_email_sent = True
                    
            # Recovery from critical high voltage alert - SEND ONLY ONCE
            elif self.voltage_critical_high_sent and not self.recovery_email_sent:
                subject = f"CRITICAL High Voltage Recovery: RV Battery at {voltage:.2f}V"
                message = f"""
CRITICAL High Voltage Recovery

Your RV battery voltage has returned to {voltage:.2f}V, which is below the critical high threshold of {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V.

RECOVERY STATUS:
- Voltage is now in safer operating range
- Critical high voltage condition has been cleared
- System monitoring continues

Current Status:
- Charger: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}
- Critical high threshold: {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V
- Normal high threshold: {VOLTAGE_THRESHOLD_HIGH}V

RECOMMENDED ACTIONS:
- Continue monitoring voltage closely
- Verify what caused the high voltage (solar controller, charger settings)
- Consider system inspection to prevent recurrence

System has returned to safer operation, but investigation is still recommended.
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_recovery = now
                    # Reset critical high voltage flag and mark recovery as sent
                    self.voltage_critical_high_sent = False
                    self.recovery_email_sent = True
                    
            # Recovery from regular high voltage alert - SEND ONLY ONCE
            elif self.voltage_high_sent and not self.recovery_email_sent:
                subject = f"High Voltage Recovery: RV Battery at {voltage:.2f}V"
                message = f"""
High Voltage Recovery

Your RV battery voltage has returned to {voltage:.2f}V, which is below the safety threshold of {VOLTAGE_THRESHOLD_HIGH}V.

Current Status:
- Charger: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar: {'Active' if self.solar_detected else 'Inactive'}
- Voltage is now in normal operating range

System has returned to normal charging operation.
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_recovery = now
                    # Reset high voltage flag and mark recovery as sent
                    self.voltage_high_sent = False
                    self.recovery_email_sent = True
    
    def check_communication_failure(self):
        """Check for prolonged communication failures and send alerts"""
        if not EMAIL_NOTIFICATIONS_ENABLED:
            return
            
        now = datetime.now()
        time_since_last_read = time.time() - self.last_successful_voltage_read
        minutes_since_last_read = time_since_last_read / 60
        
        cooldown_period = timedelta(minutes=EMAIL_COOLDOWN_MINUTES)
        
        # Critical communication failure (30+ minutes)
        if minutes_since_last_read >= COMM_FAILURE_CRITICAL_MINUTES:
            if not self.comm_failure_sent or (
                self.last_email_comm_failure and now - self.last_email_comm_failure > cooldown_period
            ):
                subject = f"CRITICAL: Battery Monitor Communication Failure - {minutes_since_last_read:.0f} Minutes!"
                message = f"""
CRITICAL COMMUNICATION FAILURE!

Your RV battery monitoring system has been unable to read voltage for {minutes_since_last_read:.0f} minutes.

IMMEDIATE ATTENTION REQUIRED:
- Battery voltage monitoring is OFFLINE
- Unable to control charger based on voltage
- System safety features may be compromised

Troubleshooting Steps:
1. Check USB connections to battery monitor device
2. Verify VE.Direct cable connections
3. Check if USB device changed (/dev/ttyUSB0 to /dev/ttyUSB1, etc.)
4. Restart battery monitoring service
5. Check system logs for detailed error messages

System Status:
- Last successful voltage read: {datetime.fromtimestamp(self.last_successful_voltage_read).strftime('%Y-%m-%d %H:%M:%S')}
- Consecutive failures: {self.consecutive_read_failures}
- Charger: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar detection: {'Active' if self.solar_detected else 'Inactive'}

WARNING: Without voltage monitoring, the system cannot:
- Prevent battery over-discharge
- Optimize charging based on voltage
- Send voltage-based alerts
- Protect against dangerous voltage levels

Please investigate and restore communication immediately!
                """
                
                if self.send_email_notification(subject, message, is_critical=True):
                    self.last_email_comm_failure = now
                    self.comm_failure_sent = True
                    
        # Initial communication failure alert (10+ minutes)
        elif minutes_since_last_read >= COMM_FAILURE_ALERT_MINUTES:
            if not self.comm_failure_sent or (
                self.last_email_comm_failure and now - self.last_email_comm_failure > cooldown_period
            ):
                subject = f"Battery Monitor Communication Issue - {minutes_since_last_read:.0f} Minutes"
                message = f"""
Battery Monitor Communication Alert

Your RV battery monitoring system has been unable to read voltage for {minutes_since_last_read:.0f} minutes.

Current Status:
- Last successful voltage read: {datetime.fromtimestamp(self.last_successful_voltage_read).strftime('%Y-%m-%d %H:%M:%S')}
- Consecutive failures: {self.consecutive_read_failures}
- System is attempting automatic recovery

Possible Causes:
- USB device connection issue
- VE.Direct cable disconnected
- Battery monitor device powered off
- USB device enumeration changed

The system will continue attempting to reconnect automatically.
If this persists beyond {COMM_FAILURE_CRITICAL_MINUTES} minutes, immediate attention will be required.

Monitor the situation and check connections if convenient.
                """
                
                if self.send_email_notification(subject, message):
                    self.last_email_comm_failure = now
                    self.comm_failure_sent = True
        
        # Recovery notification
        elif self.comm_failure_sent and minutes_since_last_read < 2:  # Communication restored
            subject = f"Battery Monitor Communication Restored"
            message = f"""
Communication Recovery

Your RV battery monitoring system has successfully restored communication.

Recovery Details:
- Communication restored at: {datetime.fromtimestamp(self.last_successful_voltage_read).strftime('%Y-%m-%d %H:%M:%S')}
- Outage duration: {minutes_since_last_read:.1f} minutes
- Current voltage: {self.last_voltage:.2f}V
- System status: Operational

All monitoring and safety features have been restored.
Normal battery monitoring operation has resumed.
            """
            
            if self.send_email_notification(subject, message):
                self.comm_failure_sent = False  # Reset flag after recovery
        
    def control_charger(self, should_connect, reason):
        """Control charger connection via relay"""
        # Clear first decision flag after first control decision
        if self.first_decision:
            self.first_decision = False
            
        if should_connect and not self.charger_connected:
            GPIO.output(RELAY_PIN, GPIO.LOW)
            self.charger_connected = True
            logging.info(f"🟢 CHARGER CONNECTED - {reason}")
            
            # Track state change
            self.charger_state_changes.append((time.time(), 'connected', reason))
            self.check_rapid_toggling()
            
        elif not should_connect and self.charger_connected:
            GPIO.output(RELAY_PIN, GPIO.HIGH)
            self.charger_connected = False
            logging.warning(f"🔴 CHARGER DISCONNECTED - {reason}")
            
            # Track state change
            self.charger_state_changes.append((time.time(), 'disconnected', reason))
            self.check_rapid_toggling()
    
    def check_rapid_toggling(self):
        """Check if charger is toggling too rapidly and send alert"""
        if len(self.charger_state_changes) < 4:
            return
        
        # Check if we have 4+ toggles within 5 minutes (300 seconds)
        # With proper hysteresis, ANY rapid toggling indicates a logic problem
        now = time.time()
        recent_changes = [change for change in self.charger_state_changes if now - change[0] <= 300]
        
        if len(recent_changes) >= 4:
            # Rapid toggling detected!
            # Only send alert once per hour to avoid spam
            if self.last_rapid_toggle_alert is None or (now - self.last_rapid_toggle_alert) > 3600:
                self.last_rapid_toggle_alert = now
                
                # Build toggle history for email
                toggle_history = []
                for timestamp, state, reason in recent_changes:
                    time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
                    toggle_history.append(f"  - {time_str}: {state.upper()} ({reason})")
                
                subject = f"⚠️ RAPID CHARGER TOGGLING DETECTED - {len(recent_changes)} changes in 5 minutes"
                message = f"""
RAPID CHARGER TOGGLING ALERT!

Your battery charger has toggled {len(recent_changes)} times within the last 5 minutes.
This indicates a LOGIC BUG - with proper hysteresis, rapid toggling should never occur.

Recent Toggle History:
{chr(10).join(toggle_history)}

Current System Status:
- Battery Voltage: {self.last_voltage:.2f}V
- Charger Status: {'Connected' if self.charger_connected else 'Disconnected'}
- Solar Status: {'Active' if self.solar_detected else 'Inactive'}
- Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Possible Causes:
- Voltage hovering near threshold boundaries
- Conflicting charging logic rules
- Solar detection flickering on/off
- Hysteresis bands too narrow

Recommended Actions:
- Review recent logs for pattern
- Check voltage thresholds in config
- Verify solar detection is stable
- Consider adjusting hysteresis bands

This alert will not repeat for 1 hour to avoid spam.
                """
                
                logging.warning(f"⚠️ RAPID TOGGLING DETECTED: {len(recent_changes)} changes in 5 minutes")
                self.send_email_notification(subject, message)
            
    def log_detailed_status(self, voltage):
        """Log detailed system status periodically"""
        now = time.time()
        if now - self.last_detailed_log < LOG_INTERVAL:
            return
            
        self.last_detailed_log = now
        current_time = datetime.now().strftime("%H:%M")
        rate_type, current_rate, has_ev_credit = self.get_current_rate_info()
        load_level = self._estimate_current_load_level()
        
        # Calculate estimated battery runtime at current load
        if voltage > 22.0:  # Only calculate if battery has reasonable charge
            current_capacity_pct = min(100, max(0, (voltage - 20.0) / 5.2 * 100))  # Rough estimate
            current_capacity_kwh = BATTERY_CAPACITY_KWH * (current_capacity_pct / 100)
            
            load_kw_estimate = {
                "minimal": 0.1, "light": 0.5, "typical": 1.0, "heavy": 1.5, "unknown": 1.0
            }.get(load_level, 1.0)
            
            estimated_runtime = current_capacity_kwh / load_kw_estimate if load_kw_estimate > 0 else 0
        else:
            estimated_runtime = 0
            current_capacity_pct = 0
        
        status_msg = (
            f"📊 DETAILED STATUS [{current_time}] - "
            f"Voltage: {voltage:.2f}V ({current_capacity_pct:.0f}%) | "
            f"Est. Runtime: {estimated_runtime:.1f}h | "
            f"Load: {load_level} | "
            f"Charger: {'Connected' if self.charger_connected else 'DISCONNECTED'} | "
            f"Solar: {'Active' if self.solar_detected else 'Inactive'} | "
            f"Rate: {current_rate:.1f}¢/kWh ({rate_type}) | "
            f"EV Credit: {'Yes' if has_ev_credit else 'No'} | "
            f"Season: {self.get_monthly_season_name()} (Solar: {self.get_solar_factor():.0%})"
        )
        
        logging.info(status_msg)
        
    def monitor_loop(self):
        """Main monitoring loop with smart charging logic"""
        
        # Check camping mode status
        is_camping, camping_voltage = self.is_camping_period()
        
        if is_camping:
            logging.info(f"🏕️ CAMPING MODE ACTIVE - Threshold: {camping_voltage}V")
            logging.info(f"🔋 Battery System: {BATTERY_CAPACITY_KWH}kWh, {TYPICAL_LOAD_KW}kW typical load")
            logging.info(f"⚡ Inverter cutoff: {INVERTER_CUTOFF_VOLTAGE}V")
            logging.info("📵 All smart charging features DISABLED - Simple high voltage protection only")
            
            # Show upcoming camping periods
            if len(CAMPING_PERIODS) > 1:
                from datetime import datetime, date
                today = date.today()
                upcoming = []
                for period in CAMPING_PERIODS:
                    start_str, end_str = period[:2]
                    try:
                        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                        if start_date > today:
                            upcoming.append(f"{start_str} to {end_str}")
                    except ValueError:
                        continue
                if upcoming:
                    logging.info(f"📅 Upcoming camping periods: {', '.join(upcoming[:2])}")
        else:
            logging.info("🚀 Starting Smart Battery Monitor with TOD Optimization...")
            logging.info(f"🔋 Battery System: {BATTERY_CAPACITY_KWH}kWh, {TYPICAL_LOAD_KW}kW typical load")
            logging.info(f"⚡ Inverter cutoff: {INVERTER_CUTOFF_VOLTAGE}V")
            logging.info(f"🚨 Voltage thresholds: Critical={CRITICAL_VOLTAGE_THRESHOLD}V, Emergency={EMERGENCY_VOLTAGE_THRESHOLD}V")
            logging.info(f"🔧 Safety thresholds: High={VOLTAGE_THRESHOLD_HIGH}V, Low={VOLTAGE_THRESHOLD_LOW}V")
            logging.info(f"⏰ Preferred hours: {PREFERRED_CHARGING_HOURS}")
            logging.info(f"🚫 Peak avoid hours: {AVOID_CHARGING_HOURS}")
            logging.info(f"☀️ Solar detection: {'Enabled' if SOLAR_DETECTION_ENABLED else 'Disabled'}")
            logging.info(f"🌐 Internet health check: {'Enabled' if INTERNET_HEALTH_CHECK_ENABLED else 'Disabled'} (Reset after {INTERNET_FAILURE_THRESHOLD} failures)")
            logging.info(f"📅 Current season: {self.get_monthly_season_name()} (Solar factor: {self.get_solar_factor():.0%}, Daylight: {self.get_monthly_daylight_hours()[0]}:00-{self.get_monthly_daylight_hours()[1]}:00)")
            
            # Show next camping period if any
            if CAMPING_PERIODS:
                from datetime import datetime, date
                today = date.today()
                next_camping = None
                for period in CAMPING_PERIODS:
                    start_str, end_str = period[:2]
                    try:
                        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                        if start_date > today:
                            if next_camping is None or start_date < next_camping[0]:
                                next_camping = (start_date, start_str, end_str)
                    except ValueError:
                        continue
                if next_camping:
                    logging.info(f"🏕️ Next camping period: {next_camping[1]} to {next_camping[2]}")
        
        try:
            while True:
                voltage = self.read_voltage()
                
                if voltage is not None:
                    # Check for voltage alerts and send emails if needed
                    self.check_voltage_alerts(voltage)
                    
                    # Check for communication failures
                    self.check_communication_failure()
                    
                    # Check internet connectivity health
                    self.check_internet_health()
                    
                    # Detect solar activity
                    self.detect_solar_charging()
                    
                    # Check if inverter needs daily reset
                    self.reset_inverter_if_needed()
                    
                    # Get current rate info
                    rate_type, current_rate, has_ev_credit = self.get_current_rate_info()
                    
                    # Determine charging decision
                    should_connect, reason = self.should_charge(voltage)
                    
                    # Control charger
                    self.control_charger(should_connect, reason)
                    
                    # Check for charging failure during EV credit hours
                    self.check_charging_failure(voltage)
                    
                    # Check for voltage stall (anytime charger is connected)
                    self.detect_voltage_stall(voltage)
                    
                    # Log to CSV
                    self.log_to_csv(voltage, reason)
                    
                    # Regular status log with rate info and voltage status
                    charger_status = "Connected" if self.charger_connected else "DISCONNECTED"
                    solar_status = "☀️" if self.solar_detected else "🌙"
                    ev_credit_status = "💰" if has_ev_credit else ""
                    voltage_status = self.get_voltage_status(voltage)
                    
                    logging.info(f"{solar_status}{ev_credit_status} {voltage:.2f}V {voltage_status} - "
                               f"Charger: {charger_status} ({reason}) - "
                               f"Rate: {current_rate:.1f}¢/kWh")
                    
                    # Detailed periodic logging
                    self.log_detailed_status(voltage)
                    
                else:
                    logging.warning("Failed to read voltage - maintaining current state")
                    # Check for prolonged communication failures even when voltage read fails
                    self.check_communication_failure()
                    # Check internet connectivity even when voltage read fails
                    self.check_internet_health()
                    
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
            # Force charger connection and inverter ON before cleanup
            logging.info("Cleanup starting - forcing charger connection and inverter ON")
            GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure charger connected
            GPIO.output(INVERTER_PIN, GPIO.LOW)  # Ensure inverter ON
            logging.info("Charger relay set to connected state, inverter set to ON")
            
            # Clean up GPIO
            GPIO.cleanup()
            logging.info("GPIO cleanup completed")
            
            # Close serial connection
            if hasattr(self, 'ser'):
                self.ser.close()
                logging.info("Serial connection closed")
                
            logging.info("Cleanup completed successfully - Charger connected")
        except Exception as e:
            logging.error(f"Cleanup error: {e}")
            # Try to force charger connection and inverter ON even if other cleanup fails
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(RELAY_PIN, GPIO.OUT)
                GPIO.setup(INVERTER_PIN, GPIO.OUT)
                GPIO.output(RELAY_PIN, GPIO.LOW)
                GPIO.output(INVERTER_PIN, GPIO.LOW)
                logging.info("Emergency charger connection and inverter ON successful")
            except Exception as e2:
                logging.error(f"Emergency charger connection failed: {e2}")
    
    def test_inverter_reset(self):
        """Test the inverter reset functionality"""
        logging.info("🧪 TESTING INVERTER RESET")
        logging.info(f"📍 Inverter pin: GPIO {INVERTER_PIN}")
        logging.info(f"⏱️  Reset duration: {INVERTER_RESET_DURATION} seconds")
        
        try:
            # Ensure inverter is ON first
            GPIO.output(INVERTER_PIN, GPIO.LOW)
            logging.info("✅ Inverter is currently ON (GPIO.LOW)")
            time.sleep(2)
            
            # Turn inverter OFF
            logging.info(f"⚡ Turning inverter OFF for {INVERTER_RESET_DURATION} seconds...")
            GPIO.output(INVERTER_PIN, GPIO.HIGH)
            
            # Count down
            for i in range(INVERTER_RESET_DURATION):
                logging.info(f"   Inverter OFF: {i+1}/{INVERTER_RESET_DURATION} seconds")
                time.sleep(1)
            
            # Turn inverter back ON
            logging.info("✅ Turning inverter back ON...")
            GPIO.output(INVERTER_PIN, GPIO.LOW)
            time.sleep(2)  # Give inverter time to stabilize
            
            logging.info("✅ TEST COMPLETE - Inverter reset successful!")
            logging.info("📊 Inverter is now ON (GPIO.LOW)")
            logging.info("⚠️  Note: GPIO pins will remain configured (no cleanup called)")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Test failed: {e}")
            # Ensure inverter is back ON even if test fails
            try:
                GPIO.output(INVERTER_PIN, GPIO.LOW)
                logging.info("🔧 Emergency recovery: Inverter set to ON")
            except:
                pass
            return False

def main():
    """Main function"""
    import sys
    
    # Check for test mode
    if len(sys.argv) > 1 and sys.argv[1] == "test-inverter":
        try:
            logging.info("🧪 Starting inverter reset test mode...")
            monitor = SmartBatteryMonitor()
            success = monitor.test_inverter_reset()
            # Don't call cleanup() - it would reset GPIO pins
            # Just close serial connection
            if hasattr(monitor, 'ser'):
                monitor.ser.close()
            logging.info("✅ Test complete - inverter remains ON, GPIO pins remain configured")
            sys.exit(0 if success else 1)
        except Exception as e:
            logging.error(f"Failed to run inverter test: {e}")
            # Ensure inverter is ON before exit
            try:
                GPIO.output(INVERTER_PIN, GPIO.LOW)
            except:
                pass
            sys.exit(1)
    
    # Normal operation
    try:
        monitor = SmartBatteryMonitor()
        monitor.monitor_loop()
    except Exception as e:
        logging.error(f"Failed to start smart battery monitor: {e}")
        try:
            GPIO.cleanup()
        except:
            pass

if __name__ == "__main__":
    main()
