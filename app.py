from flask import Flask, render_template 
from bs4 import BeautifulSoup
import requests
import time
import re
from datetime import datetime, timedelta 
import pytz
from cachelib.file import FileSystemCache
import os
import threading

# Create Flask application
application = Flask(__name__)
app = application  # This line is important for Gunicorn

# Create cache directory
cache_dir = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# Initialize cache
cache = FileSystemCache(cache_dir)

# Constants
CACHE_TIMEOUT = 4000  # 30 minutes
SCRAPE_INTERVAL = 1800  # 30 minutes
# Minimum number of teams that must parse before we trust/cache the data.
# League has 12 teams; default 10 leaves a little slack. Override via env var.
MIN_TEAMS = int(os.environ.get('MIN_TEAMS', '10'))

# Season configuration for the auto-advancing week title.
# SEASON_START = the Tuesday that begins fantasy Week 1 (the day the week
# "rolls over" after MNF). 2026 Week 1 Thursday kickoff is Sep 10, so the
# week begins Tue Sep 8, 2026. Override with the SEASON_START env var
# (format YYYY-MM-DD) each season instead of editing code.
SEASON_START = os.environ.get('SEASON_START', '2026-09-08')
TOTAL_WEEKS = int(os.environ.get('TOTAL_WEEKS', '17'))


def get_current_nfl_week():
    """Return the current fantasy week number (1..TOTAL_WEEKS) based on today.

    Weeks advance every Tuesday (00:00 US/Pacific) so the title flips to the
    next week right after Monday Night Football, matching the league's
    Tuesday-morning cadence. Falls back to Week 1 on any parsing error.
    """
    try:
        pacific = pytz.timezone('US/Pacific')
        start = pacific.localize(datetime.strptime(SEASON_START, '%Y-%m-%d'))
        now = datetime.now(pacific)
        if now < start:
            return 1
        weeks_elapsed = (now - start).days // 7
        week = weeks_elapsed + 1
        return max(1, min(week, TOTAL_WEEKS))
    except Exception as e:
        print(f"Error computing NFL week: {e}")
        return 1

WEEK_3_SCORES = {
    1: 80.44,    # Lamar-a-Lago 🙈🏨
    9: 56.60,    # Justin Time
    14: 88.64,   # Silence of the Lambs
    11: 73.94,   # StarBuckys
    8: 91.78,    # Kevin's Nifty Team
    13: 119.12,   # Teddy Confetti
    16: 92.80,     # Engage Eight
    7: 110.08,      # That's My Quarterbacks
    3: 72.32,     # CJ Off with Their Heads!
    4: 107.44,     # David's Victorious Team
    2: 93.80,     # Bo Penix Energy
    12: 112.30,     # Kamara Sutra
    5: 81.90,     # Devin's Dazzling Team
    15: 67.10,     # Josh's Mind-Blowing Team
    10: 111.50,     # LT's Legendary Team
    6: 0.00      # FAABulous
}

def scrape_team_data(url=None):
    # League URL (id 313248). Override via LEAGUE_URL env var if it ever changes.
    url = os.environ.get(
        'LEAGUE_URL',
        'https://football.fantasysports.yahoo.com/f1/313248'
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    # Yahoo standings require an authenticated session. Paste your logged-in
    # Yahoo cookie string into the YAHOO_COOKIE env var on Render.
    yahoo_cookie = os.environ.get('YAHOO_COOKIE', '').strip()
    if yahoo_cookie:
        headers['Cookie'] = yahoo_cookie
    try:
        print("Making request to Yahoo...")
        print(f"Auth cookie present: {bool(yahoo_cookie)}")
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        # Detect the login-redirect case so logs are clear
        if 'login.yahoo.com' in response.url or '<title>Login' in response.text[:2000]:
            print("WARNING: Yahoo redirected to login. YAHOO_COOKIE is missing or expired.")
        
        print(f"Got response: {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Debug: Save HTML for inspection
        with open('debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("Saved response HTML for debugging")
        
        teams_data = []
        print("Looking for tables...")
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables")
        
        for table in tables:
            headers = [th.text.strip() for th in table.find_all('th')]
            print(f"Table headers: {headers}")
            
            if 'Week Rank' in headers:
                print("Found correct table!")
                rows = table.find_all('tr')[1:]  # Skip header row
                print(f"Found {len(rows)} rows")
                
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        try:
                            team_link = cells[2].find('a', href=True)
                            if not team_link:
                                print("No team link found in cell")
                                continue
                                
                            team_href = team_link['href']
                            team_number = int(team_href.strip('/').split('/')[-1])
                            
                            team_name = cells[2].text.strip()
                            proj_cell = cells[3]
                            projected = float(proj_cell.text.strip())
                            
                            current_points = float(cells[4].text.strip()) if cells[4].text.strip() != '' else 0.0
                            
                            progress_percentage = (current_points / projected * 100) if projected > 0 else 0
                            progress_percentage = min(100, progress_percentage)
                            
                            color_class = ''
                            if 'F-positive' in proj_cell.get('class', []):
                                color_class = 'F-positive'
                            elif 'F-negative' in proj_cell.get('class', []):
                                color_class = 'F-negative'
                            
                            week3_score = WEEK_3_SCORES.get(team_number, 0.0)
                            total_points = week3_score + projected
                            
                            teams_data.append({
                                'team_name': team_name,
                                'team_number': team_number,
                                'projected_points': projected,
                                'current_points': current_points,
                                'progress_percentage': progress_percentage,
                                'color_class': color_class,
                                'week3_score': week3_score,
                                'total_points': total_points
                            })
                            print(f"Added team: {team_name} (#{team_number})")
                        except Exception as e:
                            print(f"Error processing row: {str(e)}")
                            print(f"Row HTML: {row}")
                            continue
                
                if len(teams_data) >= MIN_TEAMS:
                    return teams_data
        
        print(f"Found {len(teams_data)} teams")
        return teams_data if teams_data else None
            
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        print(f"Response status: {response.status_code if 'response' in locals() else 'No response'}")
        if 'response' in locals():
            print(f"Response content: {response.text[:500]}...")
        return None
        
def is_game_time():
    """Check if there's likely an NFL game on"""
    pacific = pytz.timezone('US/Pacific')
    now = datetime.now(pacific)
    
    # First, check if it's Thursday, Sunday, or Monday
    if now.weekday() in [3, 6, 0]:  # 3=Thursday, 6=Sunday, 0=Monday
        # For Thursday and Monday games
        if now.weekday() in [0, 3]:  # Monday or Thursday
            # 4:30 PM to 8:30 PM PT
            return (now.hour == 16 and now.minute >= 30) or \
                   (16 < now.hour < 20) or \
                   (now.hour == 20 and now.minute <= 30)
        
        # For Sunday games
        if now.weekday() == 6:  # Sunday
            # 09:00 AM to 8:30 PM PT
            return (now.hour > 9 and now.hour < 20) or \
                   (now.hour == 9 and now.minute >= 0) or \
                   (now.hour == 20 and now.minute <= 30)
            
    return False

def update_cache_in_background():
    while True:
        print("Starting cache update...")
        pacific_tz = pytz.timezone('US/Pacific')
        pacific_time = datetime.now(pacific_tz)
        print(f"Current time (PT): {pacific_time.strftime('%I:%M %p')}")
        
        teams_data = scrape_team_data()
        
        if teams_data and len(teams_data) >= MIN_TEAMS:
            teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
            cache.set('teams_data', {
                'teams': teams_data,
                'last_updated': datetime.now(pacific_tz),
            }, timeout=CACHE_TIMEOUT)
            print(f"Cache updated successfully with {len(teams_data)} teams")
        else:
            print(f"Cache update failed. Got {len(teams_data) if teams_data else 0} teams, expected >= {MIN_TEAMS}")
        
        # Determine next update interval
        if is_game_time():
            sleep_time = 300  # 5 minutes
            next_update = pacific_time + timedelta(seconds=300)
            print("Game time window active, next update in 5 minutes")
            print(f"Next update at: {next_update.strftime('%I:%M %p PT')}")
        else:
            sleep_time = 3600  # 1 hour
            next_update = pacific_time + timedelta(seconds=3600)
            print("Outside game window, next update in 1 hour")
            print(f"Next update at: {next_update.strftime('%I:%M %p PT')}")
            
        time.sleep(sleep_time)
        
def get_all_teams():
    cached = cache.get('teams_data')
    if cached:
        return cached['teams']
    
    print("Cache miss, waiting for data...")
    return []

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/')
def home():
    try:
        teams_data = get_all_teams()
        if not teams_data:
            return "Data is being collected. Please check back in a few minutes.", 503
            
        cached_data = cache.get('teams_data')
        last_updated = cached_data['last_updated'] if cached_data else datetime.now(pytz.timezone('US/Pacific'))
        
        # Sort teams by total points for display
        # teams_data.sort(key=lambda x: x['total_points'], reverse=True)
        
        # Filter out teams with 0.00 projected points
        teams_data = [team for team in teams_data if team['projected_points'] > 0]

        # Sort teams by projected points (lowest first)
        teams_data.sort(key=lambda x: x['projected_points'])  # Removed reverse=True
        
        return render_template('rankings.html',
                             teams=teams_data, 
                             last_updated=last_updated,
                             current_week=get_current_nfl_week())
            
    except Exception as e:
        print(f"Error in home route: {e}")
        return f"An error occurred: {str(e)}", 500

@app.before_first_request
def initialize_cache():
    thread = threading.Thread(target=update_cache_in_background)
    thread.daemon = True
    thread.start()

# This is important for Gunicorn
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
