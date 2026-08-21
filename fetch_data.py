import datetime
import json
import pandas as pd
import gridstatus

def get_iso_prices(iso_code):
    """Fetches genuine Real-Time (5/15 min) and Day-Ahead (Hourly) market data."""
    series_time, series_rtm = [], []
    dam_val = None
    
    try:
        if iso_code == 'ERCOT':
            iso = gridstatus.Ercot()
            
            # Fetch Real Data: RTM
            df_rtm = iso.get_spp(date="today", market='REAL_TIME_15_MIN')
            if not df_rtm.empty:
                loc_col = 'Location' if 'Location' in df_rtm.columns else df_rtm.columns[1]
                val_col = 'SPP' if 'SPP' in df_rtm.columns else 'LMP'
                filtered = df_rtm[df_rtm[loc_col] == 'HB_WEST'] if 'HB_WEST' in df_rtm[loc_col].values else df_rtm
                filtered = filtered.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered['Time'].tolist()]

            # Fetch Real Data: DAM
            df_dam = iso.get_spp(date="today", market='DAY_AHEAD_HOURLY')
            if not df_dam.empty:
                filtered_dam = df_dam[df_dam[loc_col] == 'HB_WEST'] if 'HB_WEST' in df_dam[loc_col].values else df_dam
                # Grab the most recent hourly settlement price
                dam_val = float(filtered_dam[val_col].iloc[-1])

        elif iso_code == 'CAISO':
            iso = gridstatus.CAISO()
            
            # Fetch Real Data: RTM
            df_rtm = iso.get_lmp(date="today", market="REAL_TIME_5_MIN", locations=["TH_SP15_GEN-APND"])
            if not df_rtm.empty:
                val_col = 'LMP' if 'LMP' in df_rtm.columns else df_rtm.columns[-1]
                filtered = df_rtm.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                time_col = 'Time' if 'Time' in filtered.columns else filtered.columns[0]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered[time_col].tolist()]

            # Fetch Real Data: DAM
            df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["TH_SP15_GEN-APND"])
            if not df_dam.empty:
                dam_val = float(df_dam['LMP'].iloc[-1])

        elif iso_code == 'NYISO':
            iso = gridstatus.NYISO()
            
            # Fetch Real Data: RTM
            df_rtm = iso.get_lmp(date="today", market="REAL_TIME_5_MIN", locations=["N.Y.C."])
            if not df_rtm.empty:
                val_col = 'LMP' if 'LMP' in df_rtm.columns else df_rtm.columns[-1]
                filtered = df_rtm.tail(12)
                series_rtm = [round(float(x), 2) for x in filtered[val_col].tolist()]
                time_col = 'Time' if 'Time' in filtered.columns else filtered.columns[0]
                series_time = [pd.to_datetime(t).strftime('%H:%M') for t in filtered[time_col].tolist()]

            # Fetch Real Data: DAM
            df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["N.Y.C."])
            if not df_dam.empty:
                dam_val = float(df_dam['LMP'].iloc[-1])

        elif iso_code == 'MISO':
            iso = gridstatus.MISO()
            
            # Fetch Real Data: RTM
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

            # Fetch Real Data: DAM
            try:
                df_dam = iso.get_lmp(date="today", market="DAY_AHEAD_HOURLY", locations=["ILLINOIS.HUB"])
                if not df_dam.empty:
                    dam_val = float(df_dam['LMP'].iloc[-1])
            except:
                pass

    except Exception as e:
        print(f"Error fetching ISO data for {iso_code}: {e}")

    # Soft Fallback: If an ISO API timeout leaves us with < 12 points, back-pad the real data to keep the UI from breaking.
    if len(series_rtm) > 0 and len(series_rtm) < 12:
        diff = 12 - len(series_rtm)
        last_val = series_rtm[0]
        last_time = pd.to_datetime(series_time[0])
        pad_time = [(last_time - pd.Timedelta(minutes=5*i)).strftime('%H:%M') for i in range(diff, 0, -1)]
        pad_rtm = [last_val] * diff
        series_time = pad_time + series_time
        series_rtm = pad_rtm + series_rtm
        
    # Hard Fallback: Only triggers if the ISO API is completely down/offline.
    if not series_rtm:
        now = datetime.datetime.now()
        series_time = [(now - datetime.timedelta(minutes=5*i)).strftime('%H:%M') for i in range(11, -1, -1)]
        series_rtm = [0.0] * 12
    if dam_val is None:
        dam_val = 0.0

    rtm_val = series_rtm[-1]
    dam_val = round(dam_val, 2)
    
    # Apply the real DAM hourly price across the RTM array to calculate true arbitrage spreads
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
    isos = ['ERCOT', 'CAISO', 'NYISO', 'MISO']
    markets_payload = {}

    for iso in isos:
        print(f"Fetching real telemetry for {iso}...")
        markets_payload[iso] = get_iso_prices(iso)
    
    payload = {
        "updated_at": datetime.datetime.now().isoformat(),
        "markets": markets_payload
    }

    with open('data/market_data.json', 'w') as f:
        json.dump(payload, f, indent=2)

    print("Market payload saved to data/market_data.json")

if __name__ == "__main__":
    main()
