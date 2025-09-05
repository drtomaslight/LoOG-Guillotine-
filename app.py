from flask import Flask, render_template 
from bs4 import BeautifulSoup
import requests
import time
import re
from datetime import datetime
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

def scrape_team_data(url=None):
    url = 'https://football.fantasysports.yahoo.com/f1/723352'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        teams_data = []
        
        # Find the correct table
        tables = soup.find_all('table')
        for table in tables:
            headers = [th.text.strip() for th in table.find_all('th')]
            if 'Week Rank' in headers:
                # Process each row
                for row in table.find_all('tr')[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        try:
                            # Get team number from the link
                            team_link = cells[2].find('a', href=True)
                            if not team_link:
                                continue
                                
                            team_href = team_link['href']
                            team_number = int(team_href.strip('/').split('/')[-1])
                            
                            team_name = cells[2].text.strip()
                            proj_cell = cells[3]
                            projected = float(proj_cell.text.strip())
                            
                            # Get current points from the fourth column
                            current_points = float(cells[4].text.strip()) if cells[4].text.strip() != '' else 0.0
                            
                            # Calculate progress percentage
                            progress_percentage = (current_points / projected * 100) if projected > 0 else 0
                            progress_percentage = min(100, progress_percentage)  # Cap at 100%
                            
                            # Get the color class
                            color_class = ''
                            if 'F-positive' in proj_cell.get('class', []):
                                color_class = 'F-positive'
                            elif 'F-negative' in proj_cell.get('class', []):
                                color_class = 'F-negative'
                            
                            teams_data.append({
                                'team_name': team_name,
                                'team_number': team_number,
                                'projected_points': projected,
                                'current_points': current_points,
                                'progress_percentage': progress_percentage,
                                'color_class': color_class
                            })
                            print(f"Found team: {team_name} (#{team_number}) - Projected: {projected}, Current: {current_points}, Progress: {progress_percentage:.2f}% [{color_class}]")
                        except (ValueError, IndexError) as e:
                            print(f"Error processing row: {e}")
                            continue
                            
                if len(teams_data) == 16:
                    return teams_data
                
        print(f"Found {len(teams_data)} teams")
        return teams_data if teams_data else None
            
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None
        
def is_game_time():
    """Check if there's likely an NFL game on"""
    pacific = pytz.timezone('US/Pacific')
    now = datetime.now(pacific)
    
    # First, check if it's Thursday, Sunday, or Monday
    if now.weekday() in [3, 6, 0]:  # 3=Thursday, 6=Sunday, 0=Monday
        # For Thursday and Monday games
        if now.weekday() in [0, 3]:  # Monday or Thursday
            # 5:15 PM to 8:30 PM PT
            return (now.hour == 17 and now.minute >= 15) or \
                   (17 < now.hour < 20) or \
                   (now.hour == 20 and now.minute <= 30)
        
        # For Sunday games
        if now.weekday() == 6:  # Sunday
            # 10:00 AM to 8:30 PM PT
            return (now.hour > 10 and now.hour < 20) or \
                   (now.hour == 10 and now.minute >= 0) or \
                   (now.hour == 20 and now.minute <= 30)
            
    return False

def update_cache_in_background():
    while True:
        print("Starting cache update...")
        pacific_time = datetime.now(pytz.timezone('US/Pacific'))
        print(f"Current time (PT): {pacific_time.strftime('%I:%M %p')}")
        
        teams_data = scrape_team_data()
        
        if teams_data and len(teams_data) == 16:
            teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
            cache.set('teams_data', {
                'teams': teams_data,
                'last_updated': datetime.now(pytz.timezone('US/Pacific')),
            }, timeout=CACHE_TIMEOUT)
            print(f"Cache updated successfully with {len(teams_data)} teams")
        else:
            print(f"Cache update failed. Got {len(teams_data) if teams_data else 0} teams, expected 16")
        
        # Determine next update interval
        if is_game_time():
            sleep_time = 300  # 5 minutes
            print("Game time window active (TNF/SNF/MNF), next update in 5 minutes")
            print(f"Next update at: {(pacific_time + timedelta(seconds=300)).strftime('%I:%M %p PT')}")
        else:
            sleep_time = 3600  # 1 hour
            print("Outside game window, next update in 1 hour")
            print(f"Next update at: {(pacific_time + timedelta(seconds=3600)).strftime('%I:%M %p PT')}")
            
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
        cached_data = cache.get('teams_data')
        
        if not teams_data:
            return "Data is being collected. Please check back in a few minutes.", 503
            
        last_updated = cached_data['last_updated'] if cached_data else datetime.now(pytz.timezone('US/Pacific'))
        
        return render_template('rankings.html',
                             teams=teams_data, 
                             last_updated=last_updated)
            
    except Exception as e:
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
