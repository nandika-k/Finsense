"""
Keep-alive script to ping Render deployment every 14 minutes.
Prevents the free tier from spinning down due to inactivity.
"""

import time
import requests
from datetime import datetime
import os

# Your Render deployment URL
RENDER_URL = os.getenv("RENDER_URL", "https://finsense-web.vercel.app/")
PING_INTERVAL = 14 * 60  # 14 minutes in seconds

def ping_server():
    """Send a health check ping to the server"""
    try:
        response = requests.get(RENDER_URL, timeout=10)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if response.status_code == 200:
            print(f"[{timestamp}] ✓ Ping successful - Status: {response.status_code}")
        else:
            print(f"[{timestamp}] ⚠ Ping returned status: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] ✗ Ping failed: {str(e)[:100]}")
    except Exception as e:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] ✗ Unexpected error: {str(e)[:100]}")


def main():
    """Main keep-alive loop"""
    print("="*60)
    print("FINSENSE KEEP-ALIVE SERVICE")
    print("="*60)
    print(f"Target URL: {RENDER_URL}")
    print(f"Ping interval: {PING_INTERVAL} seconds ({PING_INTERVAL//60} minutes)")
    print("Press Ctrl+C to stop\n")
    
    # Initial ping
    ping_server()
    
    try:
        while True:
            time.sleep(PING_INTERVAL)
            ping_server()
            
    except KeyboardInterrupt:
        print("\n\nKeep-alive service stopped by user")
        print("="*60)


if __name__ == "__main__":
    main()
