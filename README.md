# Battery Voltage Monitor with Charger Control

This system monitors a 6S battery voltage via VE.Direct protocol and automatically controls a charger relay for safety.

## Safety Logic

- **Relay OFF** (GPIO.LOW) = Charger CONNECTED
- **Relay ON** (GPIO.HIGH) = Charger DISCONNECTED (safety)

### Voltage Thresholds
- **High Threshold**: 24.8V - Disconnect charger above this voltage
- **Low Threshold**: 24.5V - Reconnect charger below this voltage
- **Hysteresis**: Prevents rapid on/off cycling

## Files

### Main Scripts
- `battery_monitor.py` - Main monitoring system (run continuously)
- `manual_control.py` - Manual testing and control
- `test_battery_monitor.py` - Test relay logic without serial connection

### Legacy Scripts
- `relay.py` - Original relay test script
- `voltage.py` - Original voltage reading script
- `test_relay.py` / `test_relay_off.py` - Simple relay tests

### Service
- `battery-monitor.service` - Systemd service file for auto-start

## Usage

### 1. Test the System
```bash
# Test relay logic without voltage sensor
sudo python3 test_battery_monitor.py

# Read current voltage
python3 manual_control.py voltage

# Test manual control
python3 manual_control.py connect
python3 manual_control.py disconnect
python3 manual_control.py status
```

### 2. Run Monitoring
```bash
# Run once (foreground)
sudo python3 battery_monitor.py

# Install as system service (auto-start)
sudo cp battery-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable battery-monitor
sudo systemctl start battery-monitor

# Check service status
sudo systemctl status battery-monitor

# View logs
sudo journalctl -u battery-monitor -f
```

### 3. Configuration

Edit `battery_monitor.py` to adjust:
- `VOLTAGE_THRESHOLD_HIGH` - Disconnect threshold (default: 24.8V)
- `VOLTAGE_THRESHOLD_LOW` - Reconnect threshold (default: 24.5V)
- `MONITOR_INTERVAL` - Check interval (default: 5 seconds)
- `SERIAL_PORT` - VE.Direct device (default: /dev/ttyUSB0)

## Hardware Setup

1. **Relay Module**: Connected to GPIO pin 17
   - Many relay modules are active LOW
   - Verify your module's logic before use

2. **VE.Direct Connection**: USB serial adapter on `/dev/ttyUSB0`
   - 19200 baud rate
   - Victron Energy protocol

3. **6S Battery**: Nominal voltage ~22.2V, full charge ~25.2V
   - **NEVER** exceed manufacturer's voltage limits
   - Adjust thresholds based on your specific battery

## Safety Notes

⚠️ **IMPORTANT SAFETY WARNINGS**:

1. **Test thoroughly** before connecting to actual battery/charger
2. **Verify relay logic** - some modules are active HIGH, others active LOW
3. **Set appropriate thresholds** for your specific battery chemistry
4. **Monitor logs** regularly for any issues
5. **Have manual override** capability in case of system failure

## Troubleshooting

### No Voltage Reading
- Check USB serial connection: `ls /dev/ttyUSB*`
- Verify VE.Direct wiring and protocol
- Check permissions: `sudo usermod -a -G dialout $USER`

### Relay Not Working
- Test with multimeter on GPIO pin 17
- Verify relay module power supply
- Check relay module logic (active HIGH vs LOW)

### Service Issues
- Check logs: `sudo journalctl -u battery-monitor -f`
- Verify file permissions and paths
- Ensure Python dependencies are installed

## Log Files

- System logs: `sudo journalctl -u battery-monitor`
- Application logs: `/Users/erictran/rpi/battery_monitor.log`
