#!/usr/bin/env python3
"""
Configuration file for battery monitor with time-of-day optimization
"""

# Hardware Configuration
RELAY_PIN = 17
SERIAL_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3"]  # Try USB devices 0-3
BAUD_RATE = 19200

# Voltage Thresholds
VOLTAGE_THRESHOLD_HIGH = 24.5  # Disconnect charger above this (safety)
VOLTAGE_THRESHOLD_LOW = 24.1   # Reconnect charger below this (hysteresis)
VOLTAGE_SOLAR_DETECT = 23.0    # Voltage above which we assume solar is active

# Monitoring Settings
MONITOR_INTERVAL = 30          # Seconds between voltage checks (increased for time-based)
LOG_INTERVAL = 300             # Seconds between detailed log entries (5 minutes)

# Time-of-Day Charging Schedule based on your utility rates
# Format: (start_hour, end_hour) in 24-hour format

# PREFERRED charging times (lowest cost + EV credit + solar)
PREFERRED_CHARGING_HOURS = [
    (0, 6),    # Midnight - 6 AM (EV credit -$0.0150/kWh + off-peak rates)
    (10, 17),  # 10 AM - 5 PM (solar generation + mid-peak rates, avoid peak)
    (20, 24),  # 8 PM - Midnight (off-peak rates resume)
]

# PEAK hours - avoid charging (highest cost $0.3655 summer / $0.1724 winter)
AVOID_CHARGING_HOURS = [
    (17, 20),  # 5 PM - 8 PM (peak rates - most expensive)
]

# Seasonal rate adjustments
SUMMER_SEASON = (6, 9)  # June 1 - September 30 (months 6-9)
WINTER_SEASON = (10, 5)  # October 1 - May 31 (months 10-12, 1-5)

# Rate information for logging/analysis (cents per kWh) - Updated Oct 2025
RATE_INFO = {
    'summer': {
        'off_peak': 15.05,      # Midnight-noon, weekends/holidays
        'mid_peak': 20.77,      # Noon-5PM, 8PM-midnight  
        'peak': 36.55,          # 5PM-8PM (Monday-Friday)
        'ev_credit': -1.50,     # Midnight-6AM (assuming unchanged)
    },
    'winter': {
        'off_peak': 12.48,      # Midnight-5PM, 8PM-midnight, weekends/holidays
        'peak': 17.24,          # 5PM-8PM (Monday-Friday)
        'ev_credit': -1.50,     # Midnight-6AM (assuming unchanged)
    }
}

# Voltage-based charging priority (critical for inverter protection)
INVERTER_CUTOFF_VOLTAGE = 20.3          # Your inverter shuts off at 20.3V
CRITICAL_VOLTAGE_THRESHOLD = 20.6       # Start aggressive charging at 20.6V
EMERGENCY_VOLTAGE_THRESHOLD = 21.0      # Always charge below 21.0V regardless of rates
LOW_VOLTAGE_PRIORITY_THRESHOLD = 22.0   # Prefer charging below 22.0V even during peak hours
NORMAL_VOLTAGE_THRESHOLD = 23.5         # Normal operation above 23.5V

# Solar Detection Settings
SOLAR_DETECTION_ENABLED = True
SOLAR_VOLTAGE_INCREASE_RATE = 0.1  # V/hour minimum increase to detect solar
SOLAR_DETECTION_WINDOW = 3600      # Seconds to analyze for solar detection

# Enhanced Solar Detection Methods
SOLAR_DETECTION_METHODS = {
    'voltage_trend': True,          # Original method - voltage increase over time
    'time_based': True,             # Assume solar during daylight hours
    'voltage_plateau': True,        # Detect voltage staying high during day
    'load_compensation': True,      # Account for system load patterns
}

# Time-based solar detection (backup method)
SOLAR_DAYLIGHT_HOURS = {
    'summer': (7, 19),     # 7 AM - 7 PM in summer
    'winter': (8, 17),     # 8 AM - 5 PM in winter  
    'spring': (7, 18),     # 7 AM - 6 PM in spring
    'fall': (8, 17),       # 8 AM - 5 PM in fall
}

# System Specifications
BATTERY_CAPACITY_KWH = 18.0             # 18 kWh battery system (4x 4.5kWh packs)
TYPICAL_LOAD_KW = 1.0                   # Up to 1 kW typical consumption
BATTERY_NOMINAL_VOLTAGE = 24.0          # 6S nominal voltage (24V system)
CELLS_IN_SERIES = 6                     # 6S configuration

# Load pattern detection (calculated from your system specs)
# 1 kW load on 18 kWh battery = ~18 hours runtime at full load
# Voltage drop rate: 1kW load ≈ 42A at 24V, causes faster voltage drop
TYPICAL_NIGHTTIME_VOLTAGE_DROP = 0.08   # V/hour with 1kW load (increased from 0.05)
HEAVY_LOAD_VOLTAGE_DROP = 0.15          # V/hour with full 1kW+ load
LIGHT_LOAD_VOLTAGE_DROP = 0.03          # V/hour with minimal load

# Solar detection thresholds (adjusted for your system)
SOLAR_PLATEAU_THRESHOLD = 23.8          # Higher threshold for 18kWh system
SOLAR_PLATEAU_MIN_DURATION = 1800       # 30 minutes of stable voltage = solar
SOLAR_STRONG_GENERATION_THRESHOLD = 24.2 # Voltage indicating strong solar generation

# Load-based solar detection
LOAD_COMPENSATION_ENABLED = True
EXPECTED_SOLAR_GENERATION_KW = 2.0       # Estimate your solar panel capacity (adjust as needed)

# Email Notification Settings
EMAIL_NOTIFICATIONS_ENABLED = True
EMAIL_ALERT_VOLTAGE_THRESHOLD = 21.0     # Send email alert below 21.0V
EMAIL_CRITICAL_VOLTAGE_THRESHOLD = 20.8  # Send urgent email below 20.8V
EMAIL_RECOVERY_VOLTAGE_THRESHOLD = 21.5  # Send recovery email when voltage recovers above 21.5V
EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD = 25.0  # Send critical alert above 25.0V

# Communication failure thresholds
COMM_FAILURE_ALERT_MINUTES = 10      # Alert after 10 minutes of failed voltage reads
COMM_FAILURE_CRITICAL_MINUTES = 30   # Critical alert after 30 minutes of failed reads

# Email Configuration (you'll need to set these up)
SMTP_SERVER = "smtp.gmail.com"           # Gmail SMTP server
SMTP_PORT = 587                          # Gmail SMTP port
EMAIL_FROM = "eric.n.tran@gmail.com"                          # Your email address (set this!)
EMAIL_PASSWORD = "qkiu pjeu vogc wedr"                      # App password for Gmail (set this!)
EMAIL_TO = ["eric.n.tran@gmail.com"]                            # List of email addresses to notify (set this!)

# Email notification cooldown (prevent spam)
EMAIL_COOLDOWN_MINUTES = 30              # Wait 30 minutes between similar alerts

# Logging Configuration
LOG_FILE = "/home/erictran/Script/battery_monitor.log"
VOLTAGE_LOG_FILE = "/home/erictran/Script/voltage_history.csv"
ENABLE_CSV_LOGGING = True

# Seasonal Adjustments (optional - can be expanded later)
SEASONAL_ADJUSTMENTS = {
    'winter': {'solar_hours': (11, 15)},  # Shorter solar window in winter
    'summer': {'solar_hours': (9, 17)},   # Longer solar window in summer
    'spring': {'solar_hours': (10, 16)},
    'fall': {'solar_hours': (10, 16)},
}
