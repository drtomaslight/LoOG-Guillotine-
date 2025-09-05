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
CACHE_TIMEOUT = 2000  # 30 minutes
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
                                'color_class': color_class
                            })
                            print(f"Found team: {team_name} (#{team_number}) - {projected} [{color_class}]")
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
        
def update_cache_in_background():
    while True:
        print("Starting cache update...")
        
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
        
        time.sleep(SCRAPE_INTERVAL)

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
