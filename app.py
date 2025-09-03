from flask import Flask, render_template_string
from bs4 import BeautifulSoup
import requests
import time
import re
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

@app.route('/')
def home():
    try:
        base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
        teams_data = []
        
        # Scrape all teams
        for team_num in range(1, 17):
            url = f"{base_url}{team_num}"
            print(f"Scraping team {team_num}...")
            
            team_data = scrape_team_data(url)
            if team_data:
                teams_data.append(team_data)
                print(f"Found: {team_data['team_name']} - {team_data['projected_points']}")
            time.sleep(1)
        
        teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
        last_updated = datetime.now(pytz.timezone('US/Pacific'))
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Fantasy Football Projections</title>
            <meta http-equiv="refresh" content="300">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 20px; 
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                table { 
                    border-collapse: collapse; 
                    width: 100%;
                    margin-top: 20px;
                }
                th, td { 
                    border: 1px solid #ddd; 
                    padding: 12px; 
                    text-align: left; 
                }
                th { 
                    background-color: #4CAF50; 
                    color: white; 
                }
                tr:nth-child(even) { 
                    background-color: #f2f2f2; 
                }
                tr:hover {
                    background-color: #ddd;
                }
                .last-updated {
                    color: #666;
                    font-style: italic;
                    margin-bottom: 20px;
                }
                h1 {
                    color: #333;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <h1>Fantasy Football Projected Points</h1>
            <div class="last-updated">
                Last updated: {{ last_updated.strftime('%I:%M %p PT on %B %d, %Y') }}
            </div>
            
            <table>
                <tr>
                    <th>Rank</th>
                    <th>Team Name</th>
                    <th>Projected Points</th>
                </tr>
                {% for team in teams %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td>{{ team.team_name }}</td>
                    <td>{{ "%.2f"|format(team.projected_points) }}</td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
        """
        
        return render_template_string(template, teams=teams_data, last_updated=last_updated)
            
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
