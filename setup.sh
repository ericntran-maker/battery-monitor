#!/bin/bash
# Setup script for Smart Battery Monitor

echo "🔧 Setting up Smart Battery Monitor..."

# Install Python dependencies
echo "📦 Installing Python packages..."
pip3 install pyserial pandas matplotlib

# Set up permissions for GPIO and serial
echo "🔐 Setting up permissions..."
sudo usermod -a -G gpio $USER
sudo usermod -a -G dialout $USER

# Make scripts executable
echo "⚙️ Making scripts executable..."
chmod +x /home/erictran/Script/smart_battery_monitor.py
chmod +x /home/erictran/Script/analyze_logs.py
chmod +x /home/erictran/Script/manual_control.py

# Create log directory if needed
mkdir -p /home/erictran/Script/logs

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit config.py to set your preferred charging hours"
echo "2. Test the system: sudo python3 smart_battery_monitor.py"
echo "3. Install as service: sudo cp battery-monitor.service /etc/systemd/system/"
echo "4. Enable service: sudo systemctl enable battery-monitor"
echo ""
echo "⚠️  IMPORTANT: Reboot or re-login for group permissions to take effect"
