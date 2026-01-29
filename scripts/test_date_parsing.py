"""Test date parsing for news articles"""
from datetime import datetime

test_dates = [
    '2022-12-30 00:00:00+00:00',
    '2022-12-30T00:00:00Z',
    '2022-12-30',
    '2022-12-30 00:00:00'
]

print("Testing date parsing:")
for d in test_dates:
    try:
        if '+' in d or 'Z' in d or 'T' in d:
            date_str = d.replace('Z', '+00:00') if d.endswith('Z') else d
            dt = datetime.fromisoformat(date_str)
            print(f"{d} -> {dt} (tz: {dt.tzinfo})")
            dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
            print(f"  After tz removal: {dt_naive}")
        else:
            dt = datetime.strptime(d, "%Y-%m-%d")
            print(f"{d} -> {dt}")
    except Exception as e:
        print(f"{d} -> ERROR: {e}")
