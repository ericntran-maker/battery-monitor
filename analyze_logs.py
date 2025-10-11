#!/usr/bin/env python3
"""
Log analysis utility for battery monitoring system
Analyzes voltage trends, charging patterns, and solar activity
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import sys
import os

def load_voltage_data(csv_file):
    """Load voltage data from CSV file"""
    try:
        df = pd.read_csv(csv_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def analyze_charging_patterns(df):
    """Analyze charging patterns and efficiency"""
    print("\n? CHARGING PATTERN ANALYSIS")
    print("=" * 50)
    
    # Calculate charging time percentages
    total_records = len(df)
    connected_time = len(df[df['charger_connected'] == True])
    solar_time = len(df[df['solar_detected'] == True])
    preferred_time = len(df[df['in_preferred_hours'] == True])
    avoid_time = len(df[df['in_avoid_hours'] == True])
    
    print(f"Total monitoring time: {total_records} records")
    print(f"Charger connected: {connected_time/total_records*100:.1f}% of time")
    print(f"Solar detected: {solar_time/total_records*100:.1f}% of time")
    print(f"In preferred hours: {preferred_time/total_records*100:.1f}% of time")
    print(f"In avoid hours: {avoid_time/total_records*100:.1f}% of time")
    
    # Voltage statistics
    print(f"\n? VOLTAGE STATISTICS")
    print(f"Average voltage: {df['voltage'].mean():.2f}V")
    print(f"Min voltage: {df['voltage'].min():.2f}V")
    print(f"Max voltage: {df['voltage'].max():.2f}V")
    print(f"Voltage range: {df['voltage'].max() - df['voltage'].min():.2f}V")

def plot_voltage_trends(df, days=7):
    """Plot voltage trends over time"""
    # Filter to recent days
    recent_date = df['timestamp'].max() - timedelta(days=days)
    recent_df = df[df['timestamp'] >= recent_date]
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12))
    
    # Plot 1: Voltage over time
    ax1.plot(recent_df['timestamp'], recent_df['voltage'], 'b-', linewidth=1, alpha=0.7)
    ax1.axhline(y=24.8, color='r', linestyle='--', label='High Threshold (24.8V)')
    ax1.axhline(y=24.5, color='orange', linestyle='--', label='Low Threshold (24.5V)')
    ax1.axhline(y=22.0, color='red', linestyle=':', label='Emergency (22.0V)')
    ax1.set_ylabel('Voltage (V)')
    ax1.set_title(f'Battery Voltage Trends - Last {days} Days')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Charger status
    charger_status = recent_df['charger_connected'].astype(int)
    ax2.fill_between(recent_df['timestamp'], 0, charger_status, 
                     alpha=0.3, color='green', label='Charger Connected')
    ax2.set_ylabel('Charger Status')
    ax2.set_ylim(-0.1, 1.1)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Solar detection
    solar_status = recent_df['solar_detected'].astype(int)
    ax3.fill_between(recent_df['timestamp'], 0, solar_status, 
                     alpha=0.3, color='orange', label='Solar Detected')
    ax3.set_ylabel('Solar Status')
    ax3.set_xlabel('Time')
    ax3.set_ylim(-0.1, 1.1)
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Format x-axis
    for ax in [ax1, ax2, ax3]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    plt.savefig('/home/erictran/Script/voltage_analysis.png', dpi=300, bbox_inches='tight')
    print(f"? Voltage trend plot saved to: voltage_analysis.png")

def analyze_solar_efficiency(df):
    """Analyze solar charging efficiency"""
    print("\n? SOLAR ANALYSIS")
    print("=" * 50)
    
    solar_df = df[df['solar_detected'] == True]
    if len(solar_df) == 0:
        print("No solar activity detected in logs")
        return
    
    # Solar hours analysis
    solar_df['hour'] = solar_df['timestamp'].dt.hour
    solar_by_hour = solar_df.groupby('hour').size()
    
    print("Solar activity by hour:")
    for hour, count in solar_by_hour.items():
        print(f"  {hour:02d}:00 - {count} records")
    
    # Voltage during solar vs non-solar
    solar_avg_voltage = solar_df['voltage'].mean()
    non_solar_avg_voltage = df[df['solar_detected'] == False]['voltage'].mean()
    
    print(f"\nAverage voltage during solar: {solar_avg_voltage:.2f}V")
    print(f"Average voltage without solar: {non_solar_avg_voltage:.2f}V")
    print(f"Solar voltage boost: {solar_avg_voltage - non_solar_avg_voltage:.2f}V")

def show_recent_decisions(df, hours=24):
    """Show recent charging decisions"""
    print(f"\n? RECENT CHARGING DECISIONS (Last {hours} hours)")
    print("=" * 70)
    
    recent_time = df['timestamp'].max() - timedelta(hours=hours)
    recent_df = df[df['timestamp'] >= recent_time]
    
    # Group by charging decision
    decisions = recent_df['charging_decision'].value_counts()
    
    print("Decision breakdown:")
    for decision, count in decisions.items():
        percentage = count / len(recent_df) * 100
        print(f"  {decision}: {count} times ({percentage:.1f}%)")

def main():
    csv_file = "/home/erictran/Script/voltage_history.csv"
    
    if not os.path.exists(csv_file):
        print(f"? CSV file not found: {csv_file}")
        print("Run the smart battery monitor first to generate data.")
        return
    
    print("? Loading voltage data...")
    df = load_voltage_data(csv_file)
    
    if df is None:
        return
    
    print(f"? Loaded {len(df)} records from {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Run analyses
    analyze_charging_patterns(df)
    analyze_solar_efficiency(df)
    show_recent_decisions(df)
    
    # Generate plots if matplotlib is available
    try:
        plot_voltage_trends(df)
    except ImportError:
        print("\n? Install matplotlib and pandas for voltage trend plots:")
        print("pip3 install matplotlib pandas")
    except Exception as e:
        print(f"Plot generation error: {e}")

if __name__ == "__main__":
    main()
