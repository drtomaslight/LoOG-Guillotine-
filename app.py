from flask import Flask, render_template 
from bs4 import BeautifulSoup
import requests
import time
import re
from datetime import datetime
import pytz
from cachelib.file import FileSystemCache
import os

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

def scrape_team_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # Use html.parser instead of lxml
        soup = BeautifulSoup(response.text, 'html.parser')
        
        team_name = get_team_name(soup)
        
        # Get current week
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
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    return None

def get_all_teams():
    # Try to get data from cache
    cached = cache.get('teams_data')
    if cached:
        return cached['teams']
    
    print("Cache miss or expired, scraping new data...")
    base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
    teams_data = []
    seen_teams = set()
    current_week = "Unknown Week"
    
    for team_num in range(1, 17):
        url = f"{base_url}{team_num}"
        print(f"Scraping team {team_num}...")
        
        team_data = scrape_team_data(url)
        if team_data:
            if team_data['team_name'] not in seen_teams:
                team_data['team_number'] = team_num
                teams_data.append(team_data)
                seen_teams.add(team_data['team_name'])
                current_week = team_data.get('current_week', current_week)
                print(f"Found new team: {team_data['team_name']} - {team_data['projected_points']}")
        time.sleep(0.5)

    if teams_data:
        teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
        # Store in cache for 1 minute
        cache.set('teams_data', {
            'teams': teams_data,
            'last_updated': datetime.now(pytz.timezone('US/Pacific')),
            'current_week': current_week
        }, timeout=60)
        
    return teams_data

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
