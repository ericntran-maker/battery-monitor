#!/usr/bin/env python3
"""
Test email notifications for battery monitor
"""

import sys
import os
sys.path.append('/home/erictran/Script')

from config import *
from smart_battery_monitor import SmartBatteryMonitor

def test_email_alerts():
    """Test different email alert scenarios"""
    print("🧪 Testing Email Alert System")
    print("="*50)
    
    # Check if email is configured
    if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
        print("❌ Email not configured. Run setup_email.py first.")
        return
    
    print(f"📧 Email configured:")
    print(f"   From: {EMAIL_FROM}")
    print(f"   To: {EMAIL_TO}")
    print(f"   Alert threshold: {EMAIL_ALERT_VOLTAGE_THRESHOLD}V")
    print(f"   Critical threshold: {EMAIL_CRITICAL_VOLTAGE_THRESHOLD}V")
    print(f"   High voltage threshold: {VOLTAGE_THRESHOLD_HIGH}V")
    print(f"   Critical high threshold: {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V")
    print()
    
    # Create monitor instance (but don't start monitoring)
    try:
        monitor = SmartBatteryMonitor()
    except Exception as e:
        print(f"❌ Failed to create monitor instance: {e}")
        print("Note: This is expected if running without hardware (GPIO/serial)")
        print("Creating minimal test instance...")
        
        # Create a minimal test instance for email testing only
        class TestMonitor:
            def __init__(self):
                self.charger_connected = True
                self.solar_detected = False
                self.last_voltage = 0.0
                self.voltage_alert_sent = False
                self.voltage_critical_sent = False
                self.voltage_high_sent = False
                self.voltage_critical_high_sent = False
                self.last_email_alert = None
                self.last_email_critical = None
                self.last_email_high_voltage = None
                self.last_email_critical_high = None
                self.last_email_recovery = None
            
            # Add missing methods that email system depends on
            def _estimate_current_load_level(self):
                return "test"
            
            def get_voltage_status(self, voltage):
                if voltage <= 20.6:
                    return "CRITICAL"
                elif voltage <= 21.0:
                    return "EMERGENCY"
                elif voltage <= 22.0:
                    return "LOW"
                elif voltage <= 23.5:
                    return "NORMAL"
                else:
                    return "HIGH"
            
            # Import the email methods from SmartBatteryMonitor
            def send_email_notification(self, subject, message, is_critical=False):
                return SmartBatteryMonitor.send_email_notification(self, subject, message, is_critical)
            
            def check_voltage_alerts(self, voltage):
                return SmartBatteryMonitor.check_voltage_alerts(self, voltage)
        
        monitor = TestMonitor()
    
    # Test different voltage scenarios (comprehensive test suite)
    test_scenarios = [
        (25.2, "🔴 CRITICAL HIGH voltage test (>25V)"),
        (24.7, "🟠 High voltage test (>24.5V)"),
        (23.0, "🟢 Normal voltage test"),
        (20.9, "🟡 Low voltage test"),
        (20.5, "🔴 CRITICAL LOW voltage test"),
        (21.8, "🔵 Recovery test (from low voltage)"),
        (24.2, "🔵 Recovery test (from high voltage)")
    ]
    
    for voltage, description in test_scenarios:
        print(f"Testing {description} ({voltage}V)...")
        monitor.last_voltage = voltage
        monitor.check_voltage_alerts(voltage)
        print("✅ Test completed")
        print()
        
        # Ask user to continue
        if input("Continue to next test? (y/n): ").lower() != 'y':
            break
    
    print("🎉 Email testing completed!")

def test_single_email():
    """Send a single test email to verify configuration"""
    print("📧 Testing single email notification...")
    
    if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
        print("❌ Email not configured.")
        return
    
    try:
        # Create minimal test monitor
        class TestMonitor:
            def __init__(self):
                self.charger_connected = True
                self.solar_detected = False
                self.last_voltage = 23.5
            
            # Add missing methods that email system depends on
            def _estimate_current_load_level(self):
                return "test"
            
            def get_voltage_status(self, voltage):
                if voltage <= 20.6:
                    return "CRITICAL"
                elif voltage <= 21.0:
                    return "EMERGENCY"
                elif voltage <= 22.0:
                    return "LOW"
                elif voltage <= 23.5:
                    return "NORMAL"
                else:
                    return "HIGH"
            
            def send_email_notification(self, subject, message, is_critical=False):
                return SmartBatteryMonitor.send_email_notification(self, subject, message, is_critical)
        
        monitor = TestMonitor()
        
        subject = "🧪 Battery Monitor Email Test"
        message = """
This is a test email from your RV Battery Monitor system.

If you receive this email, your email notifications are configured correctly!

Test Details:
- Email system: Working ✅
- SMTP server: Connected ✅
- Authentication: Successful ✅

Current Configuration:
- From: {EMAIL_FROM}
- To: {EMAIL_TO}
- Server: {SMTP_SERVER}:{SMTP_PORT}

Your battery monitoring system is ready to send alerts.
        """.format(
            EMAIL_FROM=EMAIL_FROM,
            EMAIL_TO=EMAIL_TO,
            SMTP_SERVER=SMTP_SERVER,
            SMTP_PORT=SMTP_PORT
        )
        
        success = monitor.send_email_notification(subject, message)
        
        if success:
            print("✅ Test email sent successfully!")
            print(f"📬 Check your inbox at: {EMAIL_TO}")
        else:
            print("❌ Failed to send test email. Check configuration.")
            
    except Exception as e:
        print(f"❌ Email test failed: {e}")

def interactive_test():
    """Interactive email testing with user input"""
    print("🎮 Interactive Email Testing")
    print("="*50)
    
    while True:
        print("\nAvailable tests:")
        print("1. 🧪 Single test email")
        print("2. 🔴 Critical high voltage alert (25V+)")
        print("3. 🟠 High voltage alert (24.5V+)")
        print("4. 🟡 Low voltage alert")
        print("5. 🔴 Critical low voltage alert")
        print("6. 🔵 Recovery notification")
        print("7. 📊 Full test suite")
        print("0. Exit")
        
        choice = input("\nSelect test (0-7): ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            test_single_email()
        elif choice == "2":
            test_specific_voltage(25.2, "Critical high voltage")
        elif choice == "3":
            test_specific_voltage(24.7, "High voltage")
        elif choice == "4":
            test_specific_voltage(20.9, "Low voltage")
        elif choice == "5":
            test_specific_voltage(20.5, "Critical low voltage")
        elif choice == "6":
            test_specific_voltage(21.8, "Recovery")
        elif choice == "7":
            test_email_alerts()
        else:
            print("Invalid choice. Please try again.")

def test_specific_voltage(voltage, description):
    """Test a specific voltage scenario by forcing the email to be sent"""
    print(f"\n🧪 Testing {description} at {voltage}V...")
    print("📧 FORCING email to be sent (bypassing normal conditions)...")
    
    try:
        # Create test monitor
        class TestMonitor:
            def __init__(self):
                self.charger_connected = True
                self.solar_detected = False
                self.last_voltage = voltage
            
            # Add missing methods that email system depends on
            def _estimate_current_load_level(self):
                return "test"
            
            def get_voltage_status(self, voltage):
                if voltage <= 20.6:
                    return "CRITICAL"
                elif voltage <= 21.0:
                    return "EMERGENCY"
                elif voltage <= 22.0:
                    return "LOW"
                elif voltage <= 23.5:
                    return "NORMAL"
                else:
                    return "HIGH"
            
            def send_email_notification(self, subject, message, is_critical=False):
                print(f"📧 Sending email: {subject}")
                success = SmartBatteryMonitor.send_email_notification(self, subject, message, is_critical)
                if success:
                    print("✅ Email sent successfully!")
                else:
                    print("❌ Email failed to send")
                return success
        
        monitor = TestMonitor()
        
        # Force send the appropriate email based on voltage range
        if voltage >= EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD:
            # Critical high voltage test
            subject = f"🧪 TEST: CRITICAL HIGH VOLTAGE ALERT - RV Battery at {voltage}V"
            message = f"""
🧪 THIS IS A TEST EMAIL 🧪

CRITICAL HIGH VOLTAGE ALERT SIMULATION!

Your RV battery voltage has reached {voltage}V, which exceeds the critical threshold of {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V.

SIMULATED SAFETY ACTIONS:
- Charger would be automatically DISCONNECTED for safety
- System would monitor voltage closely
- Investigation would be recommended

Current Test Status:
- Charger: {'Connected' if monitor.charger_connected else 'DISCONNECTED (SAFETY)'}
- Solar: {'Active' if monitor.solar_detected else 'Inactive'}
- Critical high threshold: {EMAIL_CRITICAL_HIGH_VOLTAGE_THRESHOLD}V
- Normal high threshold: {VOLTAGE_THRESHOLD_HIGH}V

This is a test of your critical high voltage alert system.
If you receive this email, your 25V+ critical alerts are working correctly!
            """
            
        elif voltage >= VOLTAGE_THRESHOLD_HIGH:
            # High voltage test
            subject = f"🧪 TEST: HIGH VOLTAGE ALERT - RV Battery at {voltage}V"
            message = f"""
🧪 THIS IS A TEST EMAIL 🧪

HIGH VOLTAGE SAFETY ALERT SIMULATION!

Your RV battery voltage has reached {voltage}V, which exceeds the safety threshold of {VOLTAGE_THRESHOLD_HIGH}V.

SIMULATED SAFETY ACTIONS:
- Charger would be automatically DISCONNECTED to prevent overcharging
- System would reconnect charger when voltage drops below {VOLTAGE_THRESHOLD_LOW}V

This is a test of your high voltage alert system.
If you receive this email, your 24.5V+ high voltage alerts are working correctly!
            """
            
        elif voltage <= EMAIL_CRITICAL_VOLTAGE_THRESHOLD:
            # Critical low voltage test
            subject = f"🧪 TEST: CRITICAL LOW VOLTAGE ALERT - RV Battery at {voltage}V"
            message = f"""
🧪 THIS IS A TEST EMAIL 🧪

CRITICAL LOW VOLTAGE ALERT SIMULATION!

Your RV battery voltage has dropped to {voltage}V, which is dangerously close to your inverter cutoff voltage of {INVERTER_CUTOFF_VOLTAGE}V.

This is a test of your critical low voltage alert system.
If you receive this email, your emergency low voltage alerts are working correctly!
            """
            
        elif voltage <= EMAIL_ALERT_VOLTAGE_THRESHOLD:
            # Low voltage test
            subject = f"🧪 TEST: LOW VOLTAGE ALERT - RV Battery at {voltage}V"
            message = f"""
🧪 THIS IS A TEST EMAIL 🧪

LOW VOLTAGE ALERT SIMULATION!

Your RV battery voltage has dropped to {voltage}V.

This is a test of your low voltage alert system.
If you receive this email, your low voltage alerts are working correctly!
            """
            
        else:
            # Recovery or normal test
            subject = f"🧪 TEST: RECOVERY/NORMAL VOLTAGE - RV Battery at {voltage}V"
            message = f"""
🧪 THIS IS A TEST EMAIL 🧪

RECOVERY/NORMAL VOLTAGE SIMULATION!

Your RV battery voltage is at {voltage}V, which is in the normal/recovery range.

This is a test of your recovery notification system.
If you receive this email, your recovery alerts are working correctly!
            """
        
        # Force send the email
        success = monitor.send_email_notification(subject, message, is_critical=True)
        
        if success:
            print("✅ Test email sent successfully!")
            print(f"📬 Check your inbox for: {subject}")
        else:
            print("❌ Test email failed to send")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--single":
            test_single_email()
        elif sys.argv[1] == "--interactive":
            interactive_test()
        elif sys.argv[1] == "--full":
            test_email_alerts()
        else:
            print("Usage:")
            print("  python3 test_email.py                # Interactive mode")
            print("  python3 test_email.py --single       # Single test email")
            print("  python3 test_email.py --interactive  # Interactive menu")
            print("  python3 test_email.py --full         # Full test suite")
    else:
        interactive_test()
