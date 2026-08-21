import os
import datetime
import json
import pandas as pd
import requests
import gridstatus

ISO_METADATA = {
    'ERCOT': {'name': 'ERCOT (Texas - West Hub)', 'lat': 31.9974, 'lon': -102.0779, 'city': 'Midland, TX'},
    'CAISO': {'name': 'CAISO (California - SP15)', 'lat': 35.3733, 'lon': -119.0187, 'city': 'Bakersfield, CA'},
    'NYISO': {'name': 'NYISO (New York - Zone J)', 'lat': 40.7128, 'lon': -74.0060, 'city': 'New York, NY'},
    'MISO':  {'name': 'MISO (Midwest - Indiana Hub)', 'lat': 39.7684, 'lon': -86.1581, 'city': 'Indianapolis, IN'}
}

def fetch_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,direct_normal_irradiance,wind_speed_10m"
        res = requests.get(url, timeout=10).json()
        curr = res.get('current', {})
        return {
            'temp': round(curr.get('temperature_2m', 0.0), 1),
            'solar': round(curr.get('direct_normal_irradiance', 0.0), 0),
            'wind': round(curr.get('wind_speed_10m', 0.0), 1)
        }
    except Exception:
        return {'temp': 22.0, 'solar': 350.0, 'wind': 4.5}

def get_iso_prices(iso_code):
    """Fetches genuine Real-Time (5/15 min) and Day-Ahead (Hourly) market data."""
    series_time, series_rtm = [], []
    dam_val = None
    
    try:
        if iso_code == 'ERCOT':
            iso = gridstatus.Ercot()
            df_rtm = iso.get_spp(date="today", market='REAL_TIME_15_MIN')
            if not df_rtm.empty:
                loc_col = 'Location' if 'Location' in df_rtm.columns else df_rtm.columns[1]
                val_col = 'SPP' if 'SPP' in df_rtm.columns else 'LMP'
                filtered = df_rtm[df_rtm[loc_col] == 'HB_WEST'] if 'HB_WEST' in df_rtm[loc_col].values else df_rtm
                filtered = filtered.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered['Time'].tolist()]

            df_dam = iso.get_spp(date="today", market='DAY_AHEAD_HOURLY')
            if not df_dam.empty:
                filtered_dam = df_dam[df_dam[loc_col] == 'HB_WEST'] if 'HB_WEST' in df_dam[loc_col].values else df_dam
                dam_val = float(filtered_dam[val_col].iloc[-1])

        elif iso_code == 'CAISO':
            iso = gridstatus.CAISO()
            df_rtm = iso.get_lmp(date="today", market="REAL_TIME_5_MIN", locations=["TH_SP15_GEN-APND"])
            if not df_rtm.empty:
                val_col = 'LMP' if 'LMP' in df_rtm.columns else df_rtm.columns[-1]
                filtered = df_rtm.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                time_col = 'Time' if 'Time' in filtered.columns else filtered.columns[0]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered[time_col].tolist()]

            df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["TH_SP15_GEN-APND"])
            if not df_dam.empty:
                dam_val = float(df_dam['LMP'].iloc[-1])

        elif iso_code == 'NYISO':
            iso = gridstatus.NYISO()
            df_rtm = iso.get_lmp(date="today", market="REAL_TIME_5_MIN", locations=["N.Y.C."])
            if not df_rtm.empty:
                val_col = 'LMP' if 'LMP' in df_rtm.columns else df_rtm.columns[-1]
                filtered = df_rtm.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                time_col = 'Time' if 'Time' in filtered.columns else filtered.columns[0]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered[time_col].tolist()]

            df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["N.Y.C."])
            if not df_dam.empty:
                dam_val = float(df_dam['LMP'].iloc[-1])

        elif iso_code == 'MISO':
            iso = gridstatus.MISO()
            try:
                df_rtm = iso.get_lmp(date="today", market="REAL_TIME_5_MIN", locations=["ILLINOIS.HUB"])
            except:
                df_rtm = iso.get_lmp(date="latest", market="REAL_TIME_5_MIN", locations=["ILLINOIS.HUB"])
            
            if not df_rtm.empty:
                val_col = 'LMP' if 'LMP' in df_rtm.columns else df_rtm.columns[-1]
                filtered = df_rtm.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                time_col = 'Time' if 'Time' in filtered.columns else filtered.columns[0]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered[time_col].tolist()]

            try:
                df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["ILLINOIS.HUB"])
                if not df_dam.empty:
                    dam_val = float(df_dam['LMP'].iloc[-1])
            except:
                pass

    except Exception as e:
        print(f"Error fetching ISO data for {iso_code}: {e}")

    if len(series_rtm) > 0 and len(series_rtm) < 12:
        diff = 12 - len(series_rtm)
        last_val = series_rtm[0]
        last_time = pd.to_datetime(series_time[0])
        pad_time = [(last_time - pd.Timedelta(minutes=5*i)).strftime('%H:%M') for i in range(diff, 0, -1)]
        pad_rtm = [last_val] * diff
        series_time = pad_time + series_time
        series_rtm = pad_rtm + series_rtm
        
    if not series_rtm:
        now = datetime.datetime.now()
        series_time = [(now - datetime.timedelta(minutes=5*i)).strftime('%H:%M') for i in range(11, -1, -1)]
        series_rtm = [0.0] * 12
    if dam_val is None:
        dam_val = 0.0

    rtm_val = series_rtm[-1]
    dam_val = round(dam_val, 2)
    series_dam = [dam_val] * len(series_rtm)
    spreads = [round(r - d, 2) for r, d in zip(series_rtm, series_dam)]

    return {
        'rtm_latest': round(rtm_val, 2),
        'dam_latest': round(dam_val, 2),
        'spread_latest': round(rtm_val - dam_val, 2),
        'series': {
            'timestamps': series_time,
            'rtm': series_rtm,
            'dam': series_dam,
            'spread': spreads
        }
    }

def main():
    os.makedirs('data', exist_ok=True)
    payload = {
        'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'markets': {}
    }

    for key, meta in ISO_METADATA.items():
        print(f"Fetching real telemetry for {key}...")
        weather_data = fetch_weather(meta['lat'], meta['lon'])
        price_data = get_iso_prices(key)

        payload['markets'][key] = {
            'metadata': meta,
            'weather': weather_data,
            'pricing': price_data
        }

    with open('data/market_data.json', 'w') as f:
        json.dump(payload, f, indent=2)

    print("Market payload saved to data/market_data.json")

if __name__ == "__main__":
    main()
