#!/usr/bin/env python3
"""
Configuration file for battery monitor with time-of-day optimization
"""

# Camping Mode - Date Range Configuration
# Format: (start_date, end_date, voltage_threshold)
CAMPING_PERIODS = [
    # Example camping periods - modify as needed
    # ("2025-10-15", "2025-10-22", 24.6),  # Week camping trip
    # ("2025-11-28", "2025-12-02", 24.5),  # Thanksgiving weekend  
    # ("2025-12-20", "2026-01-05", 24.7),  # Holiday camping
    
    # Uncomment and modify dates as needed for your camping trips
]

# Default camping voltage threshold if not specified
DEFAULT_CAMPING_VOLTAGE = 24.6

# Hardware Configuration
RELAY_PIN = 17
SERIAL_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3"]  # Try USB devices 0-3
BAUD_RATE = 19200

# Voltage Thresholds
VOLTAGE_THRESHOLD_HIGH = 24.8  # Disconnect charger above this (safety) - accounts for 1kW charging boost
VOLTAGE_THRESHOLD_LOW = 23.5   # Reconnect charger below this (hysteresis) - resting voltage
VOLTAGE_SOLAR_DETECT = 23.0    # Voltage above which we assume solar is active

# Monitoring Settings
MONITOR_INTERVAL = 60          # Seconds between voltage checks (increased for time-based)
LOG_INTERVAL = 300             # Seconds between detailed log entries (5 minutes)

# Time-of-Day Charging Schedule based on your utility rates
# Format: (start_hour, end_hour) in 24-hour format

# PREFERRED charging times (prioritize cheapest rates and solar)
PREFERRED_CHARGING_HOURS = [
    (0, 6),    # Midnight - 6 AM (EV credit -$0.0150/kWh + off-peak rates) - CHEAPEST
    (10, 17),  # 10 AM - 5 PM (solar generation window - avoid mid-peak when possible)
    # Removed 8PM-midnight: Better to wait for EV credit period for cheaper rates
]

# PEAK hours - avoid charging (highest cost $0.3655 summer / $0.1724 winter)
AVOID_CHARGING_HOURS = [
    (17, 20),  # 5 PM - 8 PM (peak rates - most expensive)
]

# Granular seasonal solar adjustments based on daylight hours and solar intensity
# Each month gets specific solar generation expectations and daylight hours
MONTHLY_SOLAR_PROFILE = {
    1:  {'name': 'Deep Winter',    'solar_factor': 0.25, 'daylight': (8, 17)},   # January - very low sun
    2:  {'name': 'Late Winter',    'solar_factor': 0.35, 'daylight': (7, 18)},   # February - still low
    3:  {'name': 'Early Spring',   'solar_factor': 0.55, 'daylight': (7, 18)},   # March - improving
    4:  {'name': 'Mid Spring',     'solar_factor': 0.75, 'daylight': (6, 19)},   # April - much better
    5:  {'name': 'Late Spring',    'solar_factor': 0.90, 'daylight': (6, 20)},   # May - very good
    6:  {'name': 'Early Summer',   'solar_factor': 1.00, 'daylight': (5, 20)},   # June - peak
    7:  {'name': 'Peak Summer',    'solar_factor': 1.00, 'daylight': (5, 20)},   # July - peak
    8:  {'name': 'Late Summer',    'solar_factor': 0.95, 'daylight': (6, 19)},   # August - still excellent
    9:  {'name': 'Early Fall',     'solar_factor': 0.80, 'daylight': (7, 18)},   # September - good
    10: {'name': 'Mid Fall',       'solar_factor': 0.60, 'daylight': (7, 17)},   # October - declining
    11: {'name': 'Late Fall',      'solar_factor': 0.40, 'daylight': (8, 17)},   # November - poor
    12: {'name': 'Early Winter',   'solar_factor': 0.20, 'daylight': (8, 17)},   # December - worst
}

# Legacy season mapping for utility rate structure (still needed for billing)
SUMMER_SEASON = (6, 9)  # June 1 - September 30 (months 6-9) - for utility rates
WINTER_SEASON = (10, 5)  # October 1 - May 31 (months 10-12, 1-5) - for utility rates

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
LOW_VOLTAGE_PRIORITY_THRESHOLD = 21.2   # Prefer charging below 21.2V even during peak hours
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

# Time-based solar detection now uses monthly profiles above
# Legacy fallback for compatibility
SOLAR_DAYLIGHT_HOURS = {
    'summer': (6, 20),     # Peak summer daylight
    'winter': (8, 17),     # Deep winter daylight  
    'spring': (7, 18),     # Spring average
    'fall': (7, 17),       # Fall average
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
