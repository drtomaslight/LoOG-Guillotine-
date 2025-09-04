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

app = Flask(__name__)

# Create cache directory
cache_dir = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# Initialize cache
cache = FileSystemCache(cache_dir)

def clean_team_name(name):
    return re.sub(r'[^a-zA-Z0-9 ]', '', name).strip()

def get_team_name(soup):
    team_name_span = soup.find('span', class_='team-name')
    if team_name_span:
        name = ''.join(s for s in team_name_span.stripped_strings)
        return clean_team_name(name)
    return "Unknown Team"

def scrape_team_data(team_num, week=1):
    url = f"https://football.fantasysports.yahoo.com/f1/723352/{team_num}/team?&week={week}&stat1=S&stat2=W"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            team_name = get_team_name(soup)
            
            week_element = soup.find('span', {'id': 'selectlist_nav'})
            current_week = week_element['title'] if week_element else f"Week {week}"
            
            proj_div = soup.find('div', class_='team-card-stats')
            if proj_div and 'Proj Points' in proj_div.text:
                proj_span = proj_div.find('span', class_='Fw-b')
                if proj_span:
                    return {
                        'team_name': team_name,
                        'team_number': teateam_num,
                        f'week_{week}_projected': float(proj_span.text.strip()),
                        'current_week': current_week
                    }
            time.sleep(1)
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error scraping {url}: {e}")
            if attempt < 2:
                time.sleep(1)
    return None

def update_cache_in_background():
    teams_data = []
    seen_teams = set()
    current_week = "Unknown Week"
    
    for team_num in range(1, 17):
        # Get Week 1 data
        team_data = scrape_team_data(team_num, week=1)
        if team_data:
            # Get Week 2 data
            week2_data = scrape_team_data(team_num, week=2)
            if week2_data:
                team_data['week_2_projected'] = week2_data['week_2_projected']
                # Calculate total
                team_data['total_projected'] = team_data['week_1_projected'] + team_data['week_2_projected']
                
            if team_data['team_name'] not in seen_teams:
                teams_data.append(team_data)
                seen_teams.add(team_data['team_name'])
                current_week = team_data.get('current_week', current_week)
        time.sleep(1)

    if teams_data:
        # Sort by total projected points
        teams_data.sort(key=lambda x: x.get('total_projected', 0), reverse=True)
        cache.set('teams_data', {
            'teams': teams_data,
            'last_updated': datetime.now(pytz.timezone('US/Pacific')),
            'current_week': current_week
        }, timeout=300)  # Cache for 5 minutes

def get_all_teams():
    # First, try to get cached data
    cached = cache.get('teams_data')
    if cached:
        # Start background update if cache is more than 4 minutes old
        age = (datetime.now(pytz.timezone('US/Pacific')) - cached['last_updated']).seconds
        if age > 240:  # 4 minutes
            thread = threading.Thread(target=update_cache_in_background)
            thread.daemon = True
            thread.start()
        return cached['teams']
    
    # If no cache, do a blocking update
    print("Cache miss, scraping new data...")
    update_cache_in_background()
    cached = cache.get('teams_data')
    return cached['teams'] if cached else []

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/')
def home():
    try:
        teams_data = get_all_teams()
        cached_data = cache.get('teams_data')
        last_updated = cached_data['last_updated'] if cached_data else datetime.now(pytz.timezone('US/Pacific'))
        current_week = cached_data.get('current_week', 'Unknown Week') if cached_data else 'Unknown Week'
        
        return render_template('rankings.html',
                             teams=teams_data, 
                             last_updated=last_updated,
                             current_week=current_week)
            
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# Start initial cache population
@app.before_first_request
def initialize_cache():
    thread = threading.Thread(target=update_cache_in_background)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
