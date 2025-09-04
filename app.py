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
import json

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
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }

    logger.info(f"Scraping team {team_num} for week {week}")
    
    for attempt in range(3):
        try:
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=10, allow_redirects=False)
            
            # Check if we're being redirected to login
            if response.status_code in (301, 302, 303, 307, 308):
                logger.error(f"Redirect detected to: {response.headers.get('Location', 'unknown')}")
                
                # Try mobile site
                mobile_url = f"https://football.m.fantasysports.yahoo.com/f1/723352/{team_num}?week={week}"
                logger.info(f"Trying mobile URL: {mobile_url}")
                response = session.get(mobile_url, headers=headers, timeout=10)
            
            response.raise_for_status()
            
            if 'login' in response.url.lower():
                logger.error("Redirected to login page")
                return None
                
            # Save the first response for debugging
            if attempt == 0:
                with open(f'team_{team_num}_week_{week}.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                logger.info(f"Saved HTML for team {team_num} week {week}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find team name and points in the saved HTML
            with open(f'team_{team_num}_week_{week}.html', 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"HTML content length: {len(content)}")
                logger.info(f"First 500 chars: {content[:500]}")
            
            team_name = None
            proj_points = None
            
            # Look for any text containing "projected" or "points"
            for element in soup.find_all(text=True):
                text = element.strip().lower()
                if 'projected' in text or 'points' in text:
                    logger.info(f"Found relevant text: {text}")
            
            if not team_name or not proj_points:
                logger.warning(f"Could not find {'team name' if not team_name else 'projection'} for team {team_num}, week {week}")
                if attempt < 2:
                    time.sleep(1)
                continue
                
            return {
                'team_name': team_name,
                'team_number': team_num,
                f'week_{week}_projected': proj_points
            }
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Error scraping {url}: {e}")
            if attempt < 2:
                time.sleep(1)
    
    return None

def update_cache_in_background():
    logger.info("Starting cache update...")
    teams_data = []
    seen_teams = set()
    
    # Try to get data from file first
    try:
        with open('teams_data.json', 'r') as f:
            cached = json.load(f)
            logger.info("Loaded data from file cache")
            return cached['teams']
    except:
        logger.info("No file cache found, scraping new data")
    
    successful_scrapes = 0
    failed_teams = []
    
    for team_num in range(1, 17):
        logger.info(f"Processing team {team_num}")
        
        team_data = scrape_team_data(team_num, week=1)
        if team_data:
            successful_scrapes += 1
            week2_data = scrape_team_data(team_num, week=2)
            
            if week2_data:
                team_data['week_2_projected'] = week2_data[f'week_2_projected']
            else:
                team_data['week_2_projected'] = 0
            
            team_data['total_projected'] = team_data[f'week_1_projected'] + team_data['week_2_projected']
            
            if team_data['team_name'] not in seen_teams:
                teams_data.append(team_data)
                seen_teams.add(team_data['team_name'])
                logger.info(f"Added team: {team_data}")
        else:
            failed_teams.append(team_num)
        
        time.sleep(1)

    if teams_data:
        logger.info(f"Successfully scraped {successful_scrapes} teams. Failed teams: {failed_teams}")
        teams_data.sort(key=lambda x: x['total_projected'], reverse=True)
        
        # Save to file cache
        try:
            with open('teams_data.json', 'w') as f:
                json.dump({
                    'teams': teams_data,
                    'last_updated': datetime.now(pytz.timezone('US/Pacific')).isoformat()
                }, f)
            logger.info("Saved data to file cache")
        except Exception as e:
            logger.error(f"Error saving to file cache: {e}")
        
        return teams_data
    else:
        logger.error("No teams were successfully scraped!")
        return []
        
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
