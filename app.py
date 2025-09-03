import requests
from bs4 import BeautifulSoup
import time
import re
from flask import Flask, render_template
from datetime import datetime
import pytz
import os
import sys

app = Flask(__name__)

# Add logging
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
        logger.info(f"Attempting to scrape {url}")
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
                logger.info(f"Found points: {points}")
                return {
                    'team_name': team_name,
                    'projected_points': points
                }
        logger.warning("Could not find projection data")
                
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Stack trace: {sys.exc_info()}")
    return None

@app.route('/')
def home():
    logger.info("Home route accessed")
    try:
        base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
        teams_data = []
        
        # Just try first team for testing
        url = f"{base_url}1"
        logger.info(f"Scraping first team from {url}")
        
        team_data = scrape_team_data(url)
        if team_data:
            teams_data.append(team_data)
            logger.info(f"Successfully scraped team: {team_data}")
        else:
            logger.warning("Failed to scrape team")
        
        last_updated = datetime.now(pytz.timezone('US/Pacific'))
        
        # Add debug response
        if not teams_data:
            return "No data found. Check logs for details.", 500
            
        return render_template('rankings.html', 
                             teams=teams_data,
                             last_updated=last_updated)
                             
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Stack trace: {sys.exc_info()}")
        return f"An error occurred: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
