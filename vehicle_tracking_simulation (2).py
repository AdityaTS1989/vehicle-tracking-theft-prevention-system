import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as patches
import warnings
warnings.filterwarnings('ignore')

# ── DARK TRACKING THEME ──────────────────────────────────────
plt.rcParams.update({
    'figure.facecolor': '#0A0E17',
    'axes.facecolor':   '#111827',
    'axes.edgecolor':   '#1F2937',
    'axes.labelcolor':  '#CBD5E1',
    'xtick.color':      '#64748B',
    'ytick.color':      '#64748B',
    'grid.color':       '#1F2937',
    'grid.alpha':       0.6,
    'text.color':       '#E2E8F0',
    'font.family':      'DejaVu Sans',
    'axes.titlepad':    14,
    'axes.titlesize':   12,
    'axes.titleweight': 'bold',
})
GREEN, BLUE, RED, ORANGE, YELLOW = '#22D3EE','#3B82F6','#F87171','#FB923C','#FACC15'
ROUTE_COLOR  = '#22D3EE'
GEOFENCE_COLOR = '#4ADE80'
ALERT_COLOR  = '#F87171'

print("✅ Imports OK")

# ── SIMULATE GPS ROUTE (PUNE AREA) ───────────────────────────
np.random.seed(42)

# Geofence center (e.g. home/office in Pune) + radius in km
GEOFENCE_CENTER = (18.6298, 73.7997)  # Talegaon area, Pune
GEOFENCE_RADIUS_KM = 3.0

# Simulate a vehicle trip: 200 GPS points over 4 hours
n_points = 200
timestamps = pd.date_range('2024-06-10 08:00', periods=n_points, freq='75s')  # ~4 hours

# Route: starts inside geofence, drives out on a delivery route, returns
t = np.linspace(0, 1, n_points)

# Create a route that goes out and comes back (loop pattern)
angle = t * 2 * np.pi
radius_profile = 0.005 + 0.012 * np.sin(np.pi * t)  # goes out then comes back
lat = GEOFENCE_CENTER[0] + radius_profile * np.cos(angle*1.3) + np.random.normal(0, 0.0008, n_points)
lon = GEOFENCE_CENTER[1] + radius_profile * np.sin(angle*1.3) + np.random.normal(0, 0.0008, n_points)

# Speed simulation (km/h) — realistic city driving
speed = np.abs(30 + 20*np.sin(t*8*np.pi) + np.random.normal(0, 5, n_points))
speed = np.clip(speed, 0, 80)
# stops (speed near 0) at some points
stop_indices = [20, 75, 140]
for idx in stop_indices:
    speed[idx:idx+4] = np.random.uniform(0, 2, 4)

# Inject a THEFT EVENT: sudden large jump + ignition off + after hours
theft_start = 165
lat[theft_start:theft_start+15] = GEOFENCE_CENTER[0] + 0.03 + np.linspace(0, 0.02, 15)
lon[theft_start:theft_start+15] = GEOFENCE_CENTER[1] + 0.035 + np.linspace(0, 0.02, 15)
speed[theft_start:theft_start+15] = np.random.uniform(40, 70, 15)

# Ignition status (1 = ON, 0 = OFF)
ignition = np.ones(n_points, dtype=int)
ignition[stop_indices[-1]:stop_indices[-1]+3] = 0  # parked briefly
ignition[theft_start-2:theft_start] = 0  # ignition off before theft (suspicious)

# ── HAVERSINE DISTANCE FROM GEOFENCE CENTER ──────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2-lat1)
    dlambda = np.radians(lon2-lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlambda/2)**2
    return 2*R*np.arcsin(np.sqrt(a))

distance_from_center = haversine(GEOFENCE_CENTER[0], GEOFENCE_CENTER[1], lat, lon)

df = pd.DataFrame({
    'timestamp': timestamps,
    'latitude': lat.round(6),
    'longitude': lon.round(6),
    'speed_kmph': speed.round(1),
    'ignition_status': ignition,
    'distance_from_home_km': distance_from_center.round(2),
})

# ── ALERT LOGIC ───────────────────────────────────────────────
GEOFENCE_BREACH_KM = GEOFENCE_RADIUS_KM
SPEED_LIMIT = 60

df['hour'] = df['timestamp'].dt.hour
df['alert_geofence_breach'] = (df['distance_from_home_km'] > GEOFENCE_BREACH_KM).astype(int)
df['alert_overspeed']       = (df['speed_kmph'] > SPEED_LIMIT).astype(int)
df['alert_after_hours_move'] = ((df['ignition_status']==1) & (df['speed_kmph']>5) &
                                  ((df['hour']>=22) | (df['hour']<5))).astype(int)
# Theft suspicion: ignition was off, then sudden movement + geofence breach
df['alert_theft_suspected'] = 0
for i in range(2, len(df)):
    if df.loc[i-1,'ignition_status']==0 and df.loc[i,'speed_kmph']>30 and df.loc[i,'distance_from_home_km']>GEOFENCE_BREACH_KM:
        df.loc[i,'alert_theft_suspected'] = 1

df['any_alert'] = df[['alert_geofence_breach','alert_overspeed','alert_after_hours_move','alert_theft_suspected']].max(axis=1)

df.to_csv('vehicle_tracking_data.csv', index=False)
print(f"✅ Generated {len(df)} GPS data points over ~4 hours")
print(f"📍 Geofence center: {GEOFENCE_CENTER}, radius: {GEOFENCE_RADIUS_KM} km")
print(f"⚠️  Geofence breaches: {df['alert_geofence_breach'].sum()}")
print(f"🚨 Theft suspected events: {df['alert_theft_suspected'].sum()}")
print(f"🏎️  Overspeed events: {df['alert_overspeed'].sum()}")

# ── CHART 1 — GPS ROUTE MAP WITH GEOFENCE ────────────────────
fig, ax = plt.subplots(figsize=(10, 9))
ax.set_facecolor('#111827')

# Geofence circle
circle = patches.Circle((GEOFENCE_CENTER[1], GEOFENCE_CENTER[0]),
                         radius=GEOFENCE_RADIUS_KM/111,  # approx degrees
                         fill=True, alpha=0.08, color=GEOFENCE_COLOR,
                         label=f'Geofence ({GEOFENCE_RADIUS_KM}km)')
circle2 = patches.Circle((GEOFENCE_CENTER[1], GEOFENCE_CENTER[0]),
                          radius=GEOFENCE_RADIUS_KM/111,
                          fill=False, edgecolor=GEOFENCE_COLOR, linewidth=2, linestyle='--')
ax.add_patch(circle)
ax.add_patch(circle2)

# Color route by alert status
normal = df[df['any_alert']==0]
alert_pts = df[df['any_alert']==1]

ax.plot(df['longitude'], df['latitude'], color=ROUTE_COLOR, linewidth=1.5, alpha=0.5, zorder=2)
ax.scatter(normal['longitude'], normal['latitude'], color=ROUTE_COLOR, s=18, alpha=0.6, label='Normal Route', zorder=3)
ax.scatter(alert_pts['longitude'], alert_pts['latitude'], color=ALERT_COLOR, s=45, label='Alert Triggered', zorder=4, edgecolors='white', linewidth=0.5)

# Home/start marker
ax.scatter(*GEOFENCE_CENTER[::-1], color=YELLOW, s=200, marker='*', label='Home Base', zorder=5, edgecolors='black', linewidth=1)

# Theft path highlight
theft_pts = df.iloc[theft_start:theft_start+15]
ax.plot(theft_pts['longitude'], theft_pts['latitude'], color=RED, linewidth=2.5, alpha=0.8, zorder=4,
        label='Theft Path (Suspected)')

ax.set_title('🗺️  Vehicle GPS Route — Geofence & Alert Map', fontsize=13)
ax.set_xlabel('Longitude'); ax.set_ylabel('Latitude')
ax.legend(framealpha=0.15, labelcolor='white', fontsize=9, loc='upper left')
ax.grid(True, alpha=0.2)
ax.set_aspect('equal')
plt.tight_layout()
plt.savefig('chart1_gps_route_map.png', dpi=150, bbox_inches='tight', facecolor='#0A0E17')
plt.close(); print("Saved chart1")

# ── CHART 2 — SPEED, DISTANCE & IGNITION TIMELINE ────────────
fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

axes[0].plot(df['timestamp'], df['speed_kmph'], color=BLUE, linewidth=1.5)
axes[0].axhline(y=SPEED_LIMIT, color=RED, linestyle='--', linewidth=1.2, alpha=0.7, label=f'Speed Limit ({SPEED_LIMIT} km/h)')
axes[0].fill_between(df['timestamp'], df['speed_kmph'], alpha=0.1, color=BLUE)
overspeed_pts = df[df['alert_overspeed']==1]
axes[0].scatter(overspeed_pts['timestamp'], overspeed_pts['speed_kmph'], color=RED, s=20, zorder=5, label='Overspeed')
axes[0].set_title('🏎️  Vehicle Speed Over Time')
axes[0].set_ylabel('Speed (km/h)')
axes[0].legend(framealpha=0.15, labelcolor='white', fontsize=8)
axes[0].grid(True, alpha=0.25)
axes[0].spines['top'].set_visible(False); axes[0].spines['right'].set_visible(False)

axes[1].plot(df['timestamp'], df['distance_from_home_km'], color=GREEN, linewidth=1.5)
axes[1].axhline(y=GEOFENCE_BREACH_KM, color=RED, linestyle='--', linewidth=1.2, alpha=0.7, label=f'Geofence Limit ({GEOFENCE_BREACH_KM} km)')
axes[1].fill_between(df['timestamp'], df['distance_from_home_km'], alpha=0.1, color=GREEN)
breach_pts = df[df['alert_geofence_breach']==1]
axes[1].scatter(breach_pts['timestamp'], breach_pts['distance_from_home_km'], color=RED, s=20, zorder=5, label='Geofence Breach')
axes[1].set_title('📍  Distance from Home Base (Geofence)')
axes[1].set_ylabel('Distance (km)')
axes[1].legend(framealpha=0.15, labelcolor='white', fontsize=8)
axes[1].grid(True, alpha=0.25)
axes[1].spines['top'].set_visible(False); axes[1].spines['right'].set_visible(False)

axes[2].fill_between(df['timestamp'], df['ignition_status'], color=ORANGE, alpha=0.4, step='post')
axes[2].plot(df['timestamp'], df['ignition_status'], color=ORANGE, linewidth=1.5, drawstyle='steps-post')
theft_pts2 = df[df['alert_theft_suspected']==1]
if len(theft_pts2)>0:
    axes[2].scatter(theft_pts2['timestamp'], theft_pts2['ignition_status'], color=RED, s=30, zorder=5, label='Theft Suspected')
axes[2].set_title('🔑  Ignition Status (1=ON, 0=OFF)')
axes[2].set_ylabel('Status'); axes[2].set_xlabel('Time')
axes[2].set_yticks([0,1]); axes[2].set_yticklabels(['OFF','ON'])
axes[2].legend(framealpha=0.15, labelcolor='white', fontsize=8)
axes[2].grid(True, alpha=0.25)
axes[2].spines['top'].set_visible(False); axes[2].spines['right'].set_visible(False)
axes[2].tick_params(axis='x', rotation=25)

plt.tight_layout()
plt.savefig('chart2_speed_distance_ignition.png', dpi=150, bbox_inches='tight', facecolor='#0A0E17')
plt.close(); print("Saved chart2")

# ── CHART 3 — ALERT SUMMARY ───────────────────────────────────
alert_counts = {
    'Geofence Breach': df['alert_geofence_breach'].sum(),
    'Overspeed': df['alert_overspeed'].sum(),
    'After-Hours Movement': df['alert_after_hours_move'].sum(),
    'Theft Suspected': df['alert_theft_suspected'].sum(),
}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
names = list(alert_counts.keys()); vals = list(alert_counts.values())
colors_alert = [GREEN, ORANGE, YELLOW, RED]
bars = ax1.barh(names, vals, color=colors_alert, alpha=0.85, edgecolor='none')
ax1.set_title('🚨  Alert Type Breakdown (4-Hour Trip)')
ax1.set_xlabel('Number of Alerts')
ax1.grid(True, axis='x', alpha=0.25)
ax1.spines['top'].set_visible(False); ax1.spines['right'].set_visible(False)
for bar, val in zip(bars, vals):
    ax1.text(val+0.2, bar.get_y()+bar.get_height()/2, str(val), va='center', color='#E2E8F0', fontsize=10)

status_counts = {'Safe Driving': (df['any_alert']==0).sum(), 'Alert Triggered': (df['any_alert']==1).sum()}
wedges, texts, autotexts = ax2.pie(
    status_counts.values(), labels=status_counts.keys(), autopct='%1.1f%%',
    colors=[GREEN, RED], startangle=90,
    wedgeprops=dict(width=0.55, edgecolor='#0A0E17', linewidth=2),
    textprops={'color':'#E2E8F0','fontsize':10})
for at in autotexts: at.set_color('#0A0E17'); at.set_fontweight('bold')
ax2.set_title('🛡️  Trip Safety Overview')

plt.tight_layout()
plt.savefig('chart3_alert_summary.png', dpi=150, bbox_inches='tight', facecolor='#0A0E17')
plt.close(); print("Saved chart3")

# ── LIVE TRACKING SIMULATION ───────────────────────────────────
print("\n" + "="*78)
print("  LIVE VEHICLE TRACKING — LAST 12 GPS PINGS")
print("="*78)
print(f"{'Time':<8} {'Lat':>10} {'Lon':>10} {'Speed':>7} {'Dist(km)':>9} {'Ignition':>9}  {'Alert'}")
print("-"*78)
for _, row in df.tail(12).iterrows():
    alert_flags = []
    if row['alert_geofence_breach']: alert_flags.append('GEOFENCE')
    if row['alert_overspeed']: alert_flags.append('SPEED')
    if row['alert_theft_suspected']: alert_flags.append('🚨THEFT')
    if row['alert_after_hours_move']: alert_flags.append('AFTER-HRS')
    alert_str = ', '.join(alert_flags) if alert_flags else '✅ OK'
    ign_str = '🟢 ON' if row['ignition_status'] else '🔴 OFF'
    print(f"{row['timestamp'].strftime('%H:%M:%S'):<8} {row['latitude']:>10.5f} {row['longitude']:>10.5f} "
          f"{row['speed_kmph']:>6.1f} {row['distance_from_home_km']:>9.2f} {ign_str:>9}  {alert_str}")
print("="*78)

# ── FINAL REPORT ─────────────────────────────────────────────
safe_pct = (df['any_alert']==0).mean()*100
max_dist = df['distance_from_home_km'].max()
max_speed = df['speed_kmph'].max()
total_alerts = int(df['any_alert'].sum())

print()
print("╔══════════════════════════════════════════════════════╗")
print("║   VEHICLE TRACKING & THEFT PREVENTION — REPORT      ║")
print("╠══════════════════════════════════════════════════════╣")
print(f"║  📅 Trip Duration     : ~4 hours (200 GPS pings)    ║")
print(f"║  📍 Geofence Radius   : {GEOFENCE_RADIUS_KM} km{'':<24}║")
print(f"║  🚗 Max Speed         : {max_speed:.1f} km/h{'':<19}║")
print(f"║  📏 Max Distance      : {max_dist:.2f} km from home{'':<13}║")
print("╠══════════════════════════════════════════════════════╣")
print(f"║  ⚠️  Geofence Breaches : {int(df['alert_geofence_breach'].sum()):<28}║")
print(f"║  🏎️  Overspeed Events  : {int(df['alert_overspeed'].sum()):<28}║")
print(f"║  🚨 Theft Suspected   : {int(df['alert_theft_suspected'].sum()):<28}║")
print(f"║  🌙 After-Hours Moves : {int(df['alert_after_hours_move'].sum()):<28}║")
print("╠══════════════════════════════════════════════════════╣")
print(f"║  ✅ Safe Driving %    : {safe_pct:.1f}%{'':<24}║")
print(f"║  🚨 Total Alerts      : {total_alerts:<28}║")
print("╠══════════════════════════════════════════════════════╣")
print("║  📁 Files Saved:                                     ║")
print("║     vehicle_tracking_data.csv                       ║")
print("║     chart1_gps_route_map.png                        ║")
print("║     chart2_speed_distance_ignition.png              ║")
print("║     chart3_alert_summary.png                        ║")
print("╚══════════════════════════════════════════════════════╝")
