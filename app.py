from flask import Flask, render_template_string
# ... (keep other imports)

app = Flask(__name__)

# ... (keep other functions)

@app.route('/')
def home():
    logger.info("Home route accessed")
    try:
        base_url = 'https://football.fantasysports.yahoo.com/f1/723352/'
        teams_data = []
        
        # Scrape all teams
        for team_num in range(1, 17):
            url = f"{base_url}{team_num}"
            logger.info(f"Scraping team {team_num} from {url}")
            
            team_data = scrape_team_data(url)
            if team_data:
                teams_data.append(team_data)
                logger.info(f"Successfully scraped team: {team_data}")
            time.sleep(1)
        
        teams_data.sort(key=lambda x: x['projected_points'], reverse=True)
        last_updated = datetime.now(pytz.timezone('US/Pacific'))
        
        # Use a simple HTML template directly in the code
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Fantasy Football Projections</title>
            <meta http-equiv="refresh" content="300">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #4CAF50; color: white; }
                tr:nth-child(even) { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>Fantasy Football Projected Points</h1>
            <p>Last updated: {{ last_updated.strftime('%I:%M %p PT on %B %d, %Y') }}</p>
            
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
        
        # Render the template string directly
        return render_template_string(template, teams=teams_data, last_updated=last_updated)
            
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Stack trace: {sys.exc_info()}")
        return f"An error occurred: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
