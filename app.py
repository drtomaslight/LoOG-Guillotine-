def scrape_team_data(url=None):
    url = 'https://football.fantasysports.yahoo.com/f1/723352'
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
            
            # Find all team name links
            teams_data = []
            team_links = soup.find_all('a', href=lambda x: x and '/f1/723352/' in x)
            
            for team_link in team_links:
                try:
                    # Get team name from link
                    team_name = team_link.text.strip()
                    
                    # Get team number from href
                    team_number = int(team_link['href'].split('/')[-1])
                    
                    # Find parent row
                    row = team_link.find_parent('tr')
                    if row:
                        # Find projected points cell
                        proj_cell = row.find('td', class_='Ta-end Va-mid Fz-xs')
                        if proj_cell:
                            proj_points = float(proj_cell.text.strip())
                            
                            teams_data.ap.append({
                                'team_name': team_name,
                                'team_number': team_number,
                                'projected_points': proj_points
                            })
                            print(f"Found team: {team_name} (#{team_number}) - {proj_points}")
                except Exception as e:
                    print(f"Error processing team: {e}")
                    continue
            
            if teams_data:
                return teams_data
                
            time.sleep(1)
            
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error scraping {url}: {e}")
            if attempt < 2:
                time.sleep(1)
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
