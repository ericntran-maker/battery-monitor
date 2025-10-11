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
        
        # State tracking
        self.charger_connected = True
        self.last_voltage = 0.0
        self.voltage_history = deque(maxlen=int(SOLAR_DETECTION_WINDOW / MONITOR_INTERVAL))
        self.last_detailed_log = 0
        self.solar_detected = False
        
        # Email notification tracking
        self.last_email_alert = None
        self.last_email_critical = None
        self.last_email_recovery = None
        self.voltage_alert_sent = False
        self.voltage_critical_sent = False
        
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
                    'rate_type', 'current_rate_cents', 'has_ev_credit', 'season', 'is_weekend'
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
                    self.get_current_season(),
                    self.is_weekend_or_holiday()
                ])
        except Exception as e:
            logging.error(f"Failed to write to CSV: {e}")
            
    def setup_gpio(self):
        """Initialize GPIO for relay control"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RELAY_PIN, GPIO.OUT)
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Start with charger connected
        logging.info("GPIO initialized - Charger connected (relay OFF)")
        
    def setup_serial(self):
        """Initialize serial connection for voltage reading"""
        try:
            self.ser = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=2)
            logging.info(f"Serial connection established on {SERIAL_PORT}")
        except Exception as e:
            logging.error(f"Failed to setup serial connection: {e}")
            raise
            
    def read_voltage(self):
        """Read voltage from VE.Direct protocol"""
        try:
            self.ser.flushInput()
            
            for _ in range(10):
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("V"):
                    mv = int(line.split("\t")[1])
                    voltage = mv / 1000.0
                    self.last_voltage = voltage
                    
                    # Add to history for solar detection
                    self.voltage_history.append((time.time(), voltage))
                    
                    return voltage
                    
            logging.warning("No voltage reading received")
            return None
            
        except Exception as e:
            logging.error(f"Error reading voltage: {e}")
            return None
            
    def detect_solar_charging(self):
        """Enhanced solar detection using multiple methods"""
        if not SOLAR_DETECTION_ENABLED or len(self.voltage_history) < 5:
            return False
            
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
        """Original voltage trend method"""
        recent_readings = list(self.voltage_history)[-10:]
        if len(recent_readings) < 5:
            return False
            
        times = [reading[0] for reading in recent_readings]
        voltages = [reading[1] for reading in recent_readings]
        
        time_diff = times[-1] - times[0]
        voltage_diff = voltages[-1] - voltages[0]
        
        if time_diff > 0:
            voltage_rate = voltage_diff / (time_diff / 3600)
            return (voltage_rate > SOLAR_VOLTAGE_INCREASE_RATE and 
                   self.last_voltage > VOLTAGE_SOLAR_DETECT)
        return False
        
    def _detect_solar_by_time(self):
        """Time-based solar detection during daylight hours"""
        now = datetime.now()
        current_hour = now.hour
        season = self.get_current_season()
        
        # Get daylight hours for current season
        if season in SOLAR_DAYLIGHT_HOURS:
            start_hour, end_hour = SOLAR_DAYLIGHT_HOURS[season]
            is_daylight = start_hour <= current_hour < end_hour
            
            # Only consider it solar if voltage is reasonable and it's daylight
            return is_daylight and self.last_voltage > VOLTAGE_SOLAR_DETECT
        
        return False
        
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
        """Determine if we're in summer or winter rate period"""
        current_month = datetime.now().month
        if 6 <= current_month <= 9:  # June-September
            return 'summer'
        else:  # October-May
            return 'winter'
            
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
        
        # Weekends are always preferred (off-peak rates all day)
        if is_weekend:
            return True
            
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
        
    def should_charge(self, voltage):
        """Determine if charging should be enabled based on voltage priority and other factors"""
        # Safety first - always disconnect if voltage too high
        if voltage >= VOLTAGE_THRESHOLD_HIGH:
            return False, "SAFETY_HIGH_VOLTAGE"
            
        # CRITICAL: Inverter protection - always charge if approaching cutoff
        if voltage <= CRITICAL_VOLTAGE_THRESHOLD:
            return True, "CRITICAL_INVERTER_PROTECTION"
            
        # Emergency charging - always charge if battery critically low
        if voltage <= EMERGENCY_VOLTAGE_THRESHOLD:
            return True, "EMERGENCY_LOW_VOLTAGE"
            
        # Low voltage priority - prefer charging even during peak hours
        if voltage <= LOW_VOLTAGE_PRIORITY_THRESHOLD:
            # Only avoid charging during peak if voltage is not too low AND solar isn't active
            if self.is_avoid_charging_time() and not self.solar_detected:
                # Still charge during peak if voltage is getting concerning
                if voltage <= (LOW_VOLTAGE_PRIORITY_THRESHOLD - 0.2):  # 22.8V
                    return True, "LOW_VOLTAGE_OVERRIDE_PEAK"
                else:
                    return False, "LOW_VOLTAGE_PEAK_AVOIDANCE"
            else:
                return True, "LOW_VOLTAGE_PRIORITY"
        
        # Normal voltage operation (above 23.0V) - use standard logic
        
        # If charger is currently connected, check if we should disconnect
        if self.charger_connected:
            # Disconnect during peak hours only if voltage is comfortable
            if self.is_avoid_charging_time() and voltage > NORMAL_VOLTAGE_THRESHOLD:
                return False, "PEAK_RATE_AVOIDANCE"
                
        # If charger is currently disconnected, check if we should reconnect
        else:
            # Only reconnect if voltage dropped below low threshold
            if voltage > VOLTAGE_THRESHOLD_LOW:
                return False, "HYSTERESIS"
                
        # Solar is active - prefer charging during solar hours
        if self.solar_detected:
            return True, "SOLAR_ACTIVE"
            
        # Check time-based preferences
        if self.is_preferred_charging_time():
            return True, "PREFERRED_HOURS"
            
        if self.is_avoid_charging_time():
            return False, "AVOID_PEAK_HOURS"
            
        # Default: maintain current state if no strong preference
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
                    '': 'CRITICAL',
                    '': 'EMERGENCY', 
                    '': 'LOW',
                    '': 'NORMAL',
                    '': 'HIGH'
                }
                for unicode_char, ascii_char in replacements.items():
                    text = text.replace(unicode_char, ascii_char)
                
                # Remove any remaining non-ASCII characters
                text = ''.join(char if ord(char) < 128 else '?' for char in text)
                return text
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = clean_ascii(EMAIL_FROM)
            msg['To'] = clean_ascii(', '.join(EMAIL_TO))
            msg['Subject'] = clean_ascii(subject)
            
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
            server.sendmail(EMAIL_FROM, EMAIL_TO, text)
            server.quit()
            
            logging.info(f"Email notification sent: {clean_ascii(subject)}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")
            return False
            
    def check_voltage_alerts(self, voltage):
        """Check voltage and send email alerts if needed"""
        if not EMAIL_NOTIFICATIONS_ENABLED:
            return
            
        now = datetime.now()
        cooldown_period = timedelta(minutes=EMAIL_COOLDOWN_MINUTES)
        
        # Critical voltage alert (most urgent)
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
- System may shut do