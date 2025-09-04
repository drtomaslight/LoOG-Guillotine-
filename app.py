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

app = Flask(__name__)

# Create cache directory
cache_dir = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# Initialize cache
cache = FileSystemCache(cache_dir)

# Constants
CACHE_TIMEOUT = 1800  # 30 minutes
SCRAPE_INTERVAL = 1800  # 30 minutes

def clean_team_name(name):
    return re.sub(r'[^a-zA-Z0-9 ]', '', name).strip()

def get_team_name(soup):
    team_name_span = soup.find('span', class_='team-name')
    if team_name_span:
        name = ''.join(s for s in team_name_span.stripped_strings)
        return clean_team_name(name)
    return "Unknown Team"

def scrape_team_data(url, retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            team_name = get_team_name(soup)
            
            week_element = soup.find('span', {'id': 'selectlist_nav'})
            current_week = week_element['title'] if week_element else "Unknown Week"
            
            proj_div = soup.find('div', class_='team-card-stats')
            if proj_div and 'Proj Points' in proj_div.text:
                proj_span = proj_div.find('span', class_='Fw-b')
                if proj_span:
                    return {
                        'team_name': team_name,
                        'projected_points': float(proj_span.text.strip()),
                        'current_week': current_week
                    }
            time.sleep(1)
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error scraping {url}: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return None

def update_cache_in_background():
    while True:
        print("Starting cache update...")
        base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
        new_teams_data = []  # Temporary list for new data
        seen_teams = set()
        current_week = "Unknown Week"
        scrape_success = True  # Flag to track if all scraping was successful
        
        # Collect all team data
        for team_num in range(1, 17):
            url = f"{base_url}{team_num}"
            team_data = scrape_team_data(url)
            if team_data:
                if team_data['team_name'] not in seen_teams:
                    team_data['team_number'] = team_num
                    new_teams_data.append(team_data)
                    seen_teams.add(team_data['team_name'])
                    current_week = team_data.get('current_week', current_week)
            else:
                print(f"Failed to get data for team {team_num}")
                scrape_success = False
                break  # Stop if any team fails
            time.sleep(1)

        # Only update cache if we successfully got all teams
        if scrape_success and len(new_teams_data) == 16:
            new_teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
            cache.set('teams_data', {
                'teams': new_teams_data,
                'last_updated': datetime.now(pytz.timezone('US/Pacific')),
                'current_week': current_week
            }, timeout=CACHE_TIMEOUT)
            print(f"Cache updated successfully with {len(new_teams_data)} teams")
        else:
            print(f"Cache update failed. Got {len(new_teams_data)} teams, expected 16")
        
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
        current_week = cached_data.get('current_week', 'Unknown Week') if cached_data else 'Unknown Week'
        
        return render_template('rankings.html',
                             teams=teams_data, 
                             last_updated=last_updated,
                             current_week=current_week)
            
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.before_first_request
def initialize_cache():
    thread = threading.Thread(target=update_cache_in_background)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
