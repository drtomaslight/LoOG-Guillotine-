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
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    logger.info(f"Scraping team {team_num} for week {week}")
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            team_name = get_team_name(soup)
            logger.info(f"Found team name: {team_name}")
            
            proj_div = soup.find('div', class_='team-card-stats')
            if proj_div and 'Proj Points' in proj_div.text:
                proj_span = proj_div.find('span', class_='Fw-b')
                if proj_span:
                    points = float(proj_span.text.strip())
                    logger.info(f"Found points for team {team_num}, week {week}: {points}")
                    return {
                        'team_name': team_name,
                        'team_number': team_num,
                        f'week_{week}_projected': points
                    }
            logger.warning(f"No projection data found for team {team_num}, week {week}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Error scraping {url}: {e}")
            if attempt < 2:
                time.sleep(1)
    return None

def update_cache_in_background():
    logger.info("Starting cache update...")
    teams_data = []
    seen_teams = set()
    
    for team_num in range(1, 17):
        # Get Week 1 data
        team_data = scrape_team_data(team_num, week=1)
        if team_data:
            # Get Week 2 data
            week2_data = scrape_team_data(team_num, week=2)
            if week2_data:
                team_data['week_2_projected'] = week2_data['week_2_projected']
                logger.info(f"Added week 2 data for team {team_num}")
            
            # Calculate total (use 0 for week 2 if not available)
            week2_points = team_data.get('week_2_projected', 0)
            team_data['total_projected'] = team_data['week_1_projected'] + week2_points
            
            if team_data['team_name'] not in seen_teams:
                teams_data.append(team_data)
                seen_teams.add(team_data['team_name'])
                logger.info(f"Added team to dataset: {team_data['team_name']}")
        time.sleep(1)

    if teams_data:
        logger.info(f"Found {len(teams_data)} teams, updating cache...")
        teams_data.sort(key=lambda x: x.get('total_projected', 0), reverse=True)
        cache.set('teams_data', {
            'teams': teams_data,
            'last_updated': datetime.now(pytz.timezone('US/Pacific'))
        }, timeout=300)
        logger.info("Cache update complete")
    else:
        logger.warning("No teams data found to cache")

def get_all_teams():
    cached = cache.get('teams_data')
    if cached:
        age = (datetime.now(pytz.timezone('US/Pacific')) - cached['last_updated']).seconds
        logger.info(f"Cache age: {age} seconds")
        if age > 240:  # 4 minutes
            logger.info("Starting background update...")
            thread = threading.Thread(target=update_cache_in_background)
            thread.daemon = True
            thread.start()
        return cached['teams']
    
    logger.info("Cache miss, scraping new data...")
    update_cache_in_background()
    cached = cache.get('teams_data')
    return cached['teams'] if cached else []

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/')
def home():
    try:
        logger.info("Home route accessed")
        teams_data = get_all_teams()
        if not teams_data:
            logger.warning("No teams data available")
            return "No data available", 500
            
        cached_data = cache.get('teams_data')
        last_updated = cached_data['last_updated'] if cached_data else datetime.now(pytz.timezone('US/Pacific'))
        
        logger.info(f"Rendering template with {len(teams_data)} teams")
        return render_template('rankings.html',
                             teams=teams_data, 
                             last_updated=last_updated)
            
    except Exception as e:
        logger.error(f"Error in home route: {e}")
        return f"An error occurred: {str(e)}", 500

@app.before_first_request
def initialize_cache():
    logger.info("Initializing cache...")
    thread = threading.Thread(target=update_cache_in_background)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
