#!/usr/bin/env python3
"""
Email Configuration Setup for Battery Monitor
Helps you configure email notifications safely
"""

import getpass
import smtplib
from email.mime.text import MIMEText

def test_email_connection(smtp_server, smtp_port, email_from, email_password, email_to):
    """Test email configuration"""
    try:
        print("Testing email connection...")
        
        # Create test message
        msg = MIMEText("This is a test message from your RV Battery Monitor setup.")
        msg['Subject'] = "? RV Battery Monitor - Email Test"
        msg['From'] = email_from
        msg['To'] = email_to
        
        # Send test email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(email_from, email_password)
        server.sendmail(email_from, [email_to], msg.as_string())
        server.quit()
        
        print("? Email test successful!")
        return True
        
    except Exception as e:
        print(f"? Email test failed: {e}")
        return False

def setup_gmail_config():
    """Interactive setup for Gmail configuration"""
    print("? Gmail Email Notification Setup")
    print("=" * 50)
    print()
    print("To use Gmail for notifications, you need:")
    print("1. A Gmail account")
    print("2. 2-Factor Authentication enabled")
    print("3. An App Password (not your regular Gmail password)")
    print()
    print("To create an App Password:")
    print("1. Go to https://myaccount.google.com/security")
    print("2. Enable 2-Step Verification if not already enabled")
    print("3. Go to 'App passwords' and generate a new password")
    print("4. Use that 16-character password below")
    print()
    
    # Get email configuration
    email_from = input("Enter your Gmail address: ").strip()
    email_password = getpass.getpass("Enter your Gmail App Password: ").strip()
    
    email_to_input = input("Enter notification email(s) (comma-separated): ").strip()
    email_to_list = [email.strip() for email in email_to_input.split(',')]
    
    # Test configuration
    print("\nTesting email configuration...")
    success = test_email_connection(
        "smtp.gmail.com", 587, email_from, email_password, email_to_list[0]
    )
    
    if success:
        # Generate config file content
        config_content = f'''
# Email Configuration - Add these lines to your config.py file

# Email Configuration (Gmail setup)
EMAIL_NOTIFICATIONS_ENABLED = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "{email_from}"
EMAIL_PASSWORD = "{email_password}"
EMAIL_TO = {email_to_list}

# Email alert thresholds
EMAIL_ALERT_VOLTAGE_THRESHOLD = 21.0     # Send email alert below 21.0V
EMAIL_CRITICAL_VOLTAGE_THRESHOLD = 20.8  # Send urgent email below 20.8V
EMAIL_RECOVERY_VOLTAGE_THRESHOLD = 21.5  # Send recovery email when voltage recovers above 21.5V
EMAIL_COOLDOWN_MINUTES = 30              # Wait 30 minutes between similar alerts
'''
        
        print("\n" + "="*60)
        print("="*60)
        print("\nAdd these lines to your config.py file:")
        print(config_content)
        
        # Offer to update config.py automatically
        update_config = input("\nWould you like me to update config.py automatically? (y/n): ").lower()
        if update_config == 'y':
            try:
                # Read current config
                with open('/home/erictran/Script/config.py', 'r') as f:
                    current_config = f.read()
                
                # Update email settings
                updated_config = current_config.replace(
                    'EMAIL_FROM = ""', f'EMAIL_FROM = "{email_from}"'
                ).replace(
                    'EMAIL_PASSWORD = ""', f'EMAIL_PASSWORD = "{email_password}"'
                ).replace(
                    'EMAIL_TO = []', f'EMAIL_TO = {email_to_list}'
                )
                
                # Write updated config
                with open('/home/erictran/Script/config.py', 'w') as f:
                    f.write(updated_config)
                
                print("? config.py updated successfully!")
                print("\nYour email notifications are now configured and ready to use.")
                
            except Exception as e:
                print(f"? Failed to update config.py: {e}")
                print("Please manually add the configuration above to config.py")
        
    else:
        print("\n? Email configuration failed. Please check your credentials and try again.")

def main():
    print("? RV Battery Monitor - Email Setup")
    print("="*50)
    
    provider = input("Email provider (gmail/other): ").lower().strip()
    
    if provider == "gmail":
        setup_gmail_config()
    else:
        print("Currently only Gmail setup is automated.")
        print("For other providers, manually configure these settings in config.py:")
        print("- SMTP_SERVER")
        print("- SMTP_PORT") 
        print("- EMAIL_FROM")
        print("- EMAIL_PASSWORD")
        print("- EMAIL_TO")

if __name__ == "__main__":
    main()
