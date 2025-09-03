import requests
from bs4 import BeautifulSoup
import time
import re
from flask import Flask, render_template
from datetime import datetime
import pytz
import os

app = Flask(__name__)

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
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        team_name = get_team_name(soup)
        
        proj_div = soup.find('div', class_='team-card-stats')
        if proj_div and 'Proj Points' in proj_div.text:
            proj_span = proj_div.find('span', class_='Fw-b')
            if proj_span:
                return {
                    'team_name': team_name,
                    'projected_points': float(proj_span.text.strip())
                }
                
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    return None

def get_all_team_data():
    base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
    teams_data = []
    
    for team_num in range(1, 17):
        url = f"{base_url}{team_num}"
        print(f"Scraping team {team_num}...", end=' ')
        
        team_data = scrape_team_data(url)
        if team_data:
            teams_data.append(team_data)
            print(f"Found: {team_data['team_name']} - {team_data['projected_points']}")
        else:
            print("Failed")
        
        time.sleep(1)
    
    teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
    return teams_data

@app.route('/')
def home():
    teams = get_all_team_data()
    last_updated = datetime.now(pytz.timezone('US/Pacific'))
    return render_template('rankings.html', 
                         teams=teams,
                         last_updated=last_updated)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
