#!/usr/bin/env python3
"""
Cost Analysis Tool for Smart Battery Monitor
Analyzes charging costs and savings from TOD optimization
"""

import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import sys
import os
from config import RATE_INFO

def load_and_analyze_costs(csv_file, days=30):
    """Load data and calculate charging costs"""
    try:
        df = pd.read_csv(csv_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Filter to recent period
        recent_date = df['timestamp'].max() - timedelta(days=days)
        df = df[df['timestamp'] >= recent_date]
        
        if len(df) == 0:
            print("No data found for analysis period")
            return None
            
        return df
        
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def calculate_charging_costs(df):
    """Calculate actual vs theoretical charging costs"""
    print("\n? CHARGING COST ANALYSIS")
    print("=" * 60)
    
    # Filter to only when charger was connected
    charging_df = df[df['charger_connected'] == True].copy()
    
    if len(charging_df) == 0:
        print("No charging periods found in data")
        return
    
    # Assume average charging power (you can adjust this)
    AVERAGE_CHARGING_POWER_KW = 1.0  # 1kW average charging power
    HOURS_PER_RECORD = 30 / 3600     # 30 seconds per record converted to hours
    
    # Calculate energy consumed and costs
    charging_df['energy_kwh'] = AVERAGE_CHARGING_POWER_KW * HOURS_PER_RECORD
    charging_df['cost_cents'] = charging_df['energy_kwh'] * charging_df['current_rate_cents']
    
    # Total costs
    total_energy = charging_df['energy_kwh'].sum()
    total_cost = charging_df['cost_cents'].sum()
    avg_rate = total_cost / total_energy if total_energy > 0 else 0
    
    print(f"? CHARGING SUMMARY (Last {len(df)/120:.1f} hours)")
    print(f"Total energy charged: {total_energy:.2f} kWh")
    print(f"Total cost: ${total_cost/100:.2f}")
    print(f"Average rate paid: {avg_rate:.2f}c/kWh")
    
    # Break down by rate type
    print(f"\n? CHARGING BY RATE PERIOD:")
    rate_breakdown = charging_df.groupby('rate_type').agg({
        'energy_kwh': 'sum',
        'cost_cents': 'sum',
        'current_rate_cents': 'mean'
    }).round(2)
    
    for rate_type, row in rate_breakdown.iterrows():
        energy = row['energy_kwh']
        cost = row['cost_cents']
        rate = row['current_rate_cents']
        percentage = (energy / total_energy * 100) if total_energy > 0 else 0
        
        print(f"  {rate_type}: {energy:.2f} kWh ({percentage:.1f}%) at {rate:.1f}c/kWh = ${cost/100:.2f}")
    
    # Calculate savings vs always charging at peak rate
    summer_peak_rate = RATE_INFO['summer']['peak']
    winter_peak_rate = RATE_INFO['winter']['peak']
    worst_case_rate = max(summer_peak_rate, winter_peak_rate)
    
    worst_case_cost = total_energy * worst_case_rate
    savings = worst_case_cost - total_cost
    savings_percentage = (savings / worst_case_cost * 100) if worst_case_cost > 0 else 0
    
    print(f"\n? SMART CHARGING SAVINGS:")
    print(f"Cost if always charged at peak rate ({worst_case_rate:.1f}c/kWh): ${worst_case_cost/100:.2f}")
    print(f"Actual smart charging cost: ${total_cost/100:.2f}")
    print(f"Total savings: ${savings/100:.2f} ({savings_percentage:.1f}%)")
    
    return charging_df

def analyze_solar_impact(df):
    """Analyze the impact of solar charging"""
    print(f"\n? SOLAR CHARGING ANALYSIS")
    print("=" * 60)
    
    solar_charging = df[(df['charger_connected'] == True) & (df['solar_detected'] == True)]
    total_charging = df[df['charger_connected'] == True]
    
    if len(total_charging) == 0:
        print("No charging data available")
        return
    
    solar_percentage = len(solar_charging) / len(total_charging) * 100
    
    print(f"Solar charging periods: {len(solar_charging)} records")
    print(f"Total charging periods: {len(total_charging)} records")
    print(f"Solar charging percentage: {solar_percentage:.1f}%")
    
    if len(solar_charging) > 0:
        avg_solar_rate = solar_charging['current_rate_cents'].mean()
        avg_non_solar_rate = df[(df['charger_connected'] == True) & (df['solar_detected'] == False)]['current_rate_cents'].mean()
        
        print(f"Average rate during solar charging: {avg_solar_rate:.1f}c/kWh")
        print(f"Average rate during non-solar charging: {avg_non_solar_rate:.1f}c/kWh")
        
        if avg_non_solar_rate > avg_solar_rate:
            print(f"Solar charging saves: {avg_non_solar_rate - avg_solar_rate:.1f}c/kWh")

def plot_cost_trends(df):
    """Plot charging costs over time"""
    try:
        charging_df = df[df['charger_connected'] == True].copy()
        
        if len(charging_df) == 0:
            print("No charging data to plot")
            return
            
        # Resample to hourly data
        charging_df.set_index('timestamp', inplace=True)
        hourly_data = charging_df.resample('H').agg({
            'current_rate_cents': 'mean',
            'charger_connected': 'sum',
            'solar_detected': 'any'
        }).fillna(0)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        
        # Plot 1: Electricity rates over time
        ax1.plot(hourly_data.index, hourly_data['current_rate_cents'], 'b-', linewidth=1)
        ax1.fill_between(hourly_data.index, 0, hourly_data['current_rate_cents'], 
                        where=hourly_data['charger_connected'] > 0, alpha=0.3, color='green', 
                        label='Charging Periods')
        ax1.set_ylabel('Rate (c/kWh)')
        ax1.set_title('Electricity Rates and Charging Periods')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Charging activity
        ax2.bar(hourly_data.index, hourly_data['charger_connected'], width=0.04, 
               alpha=0.7, color='green', label='Charging Time')
        solar_periods = hourly_data[hourly_data['solar_detected']]
        ax2.bar(solar_periods.index, solar_periods['charger_connected'], width=0.04,
               alpha=0.9, color='orange', label='Solar + Charging')
        ax2.set_ylabel('Charging Activity')
        ax2.set_xlabel('Time')
        ax2.set_title('Charging Activity (with Solar Detection)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('/home/erictran/Script/cost_analysis.png', dpi=300, bbox_inches='tight')
        print(f"? Cost analysis plot saved to: cost_analysis.png")
        
    except Exception as e:
        print(f"Error creating plots: {e}")

def show_optimization_summary(df):
    """Show how well the system is optimizing for TOD rates"""
    print(f"\n? OPTIMIZATION EFFECTIVENESS")
    print("=" * 60)
    
    # Count charging decisions
    decisions = df['charging_decision'].value_counts()
    total_decisions = len(df)
    
    print("Charging decision breakdown:")
    for decision, count in decisions.items():
        percentage = count / total_decisions * 100
        print(f"  {decision}: {count} times ({percentage:.1f}%)")
    
    # Peak avoidance effectiveness
    peak_periods = df[df['in_avoid_hours'] == True]
    peak_charging = peak_periods[peak_periods['charger_connected'] == True]
    
    if len(peak_periods) > 0:
        peak_avoidance = (1 - len(peak_charging) / len(peak_periods)) * 100
        print(f"\nPeak hour avoidance: {peak_avoidance:.1f}%")
        print(f"Peak periods: {len(peak_periods)} total, {len(peak_charging)} with charging")

def main():
    csv_file = "/home/erictran/Script/voltage_history.csv"
    
    if not os.path.exists(csv_file):
        print(f"? CSV file not found: {csv_file}")
        print("Run the smart battery monitor first to generate data.")
        return
    
    print("? Loading charging cost data...")
    df = load_and_analyze_costs(csv_file)
    
    if df is None:
        return
    
    print(f"? Loaded {len(df)} records for cost analysis")
    
    # Run analyses
    charging_df = calculate_charging_costs(df)
    analyze_solar_impact(df)
    show_optimization_summary(df)
    
    # Generate plots if possible
    try:
        plot_cost_trends(df)
    except ImportError:
        print("\n? Install matplotlib and pandas for cost trend plots:")
        print("pip3 install matplotlib pandas")
    except Exception as e:
        print(f"Plot generation error: {e}")

if __name__ == "__main__":
    main()
