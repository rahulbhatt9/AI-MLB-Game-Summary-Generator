from flask import Flask, render_template, request
import requests
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

app = Flask(__name__)

load_dotenv()

# Fetch the MLB 2024 regular season schedule
url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2024"
response = requests.get(url)

# Parse the schedule data
if response.status_code == 200:
    schedule_data = response.json()
    games = []
    
    # Loop through each date and game data
    for date_info in schedule_data['dates']:
        for game in date_info['games']:
            away_team = game['teams']['away']['team']['name']
            home_team = game['teams']['home']['team']['name']
            game_pk = game['gamePk']
            game_date = date_info['date']  # Extract game date
            games.append({"team_away": away_team, "team_home": home_team, "game_pk": game_pk, "game_date": game_date})
else:
    games = []

# Helper functions to parse game data
def fetch_game_data(game_pk):
    """
    Fetch live game data from the MLB Stats API for a specific game ID.
    
    Args:
        game_pk (int): The game ID.
        
    Returns:
        dict: Parsed JSON data from the API response.
    """
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data. Status code: {response.status_code}")
        return None

def parse_metadata(data):
    """
    Extract metadata from the game data.
    """
    metadata = data.get("metaData", {})
    return {
        "timestamp": metadata.get("timeStamp", ""),
        "game_events": metadata.get("gameEvents", []),
        "logical_events": metadata.get("logicalEvents", [])
    }

def parse_game_data(data):
    """
    Extract game details like status, datetime, and teams.
    """
    game_data = data.get("gameData", {})
    teams = game_data.get("teams", {})
    return {
        "status": game_data.get("status", {}).get("detailedState", ""),
        "datetime": game_data.get("datetime", {}).get("dateTime", ""),
        "away_team": teams.get("away", {}).get("name", "Unknown"),
        "home_team": teams.get("home", {}).get("name", "Unknown"),
        "away_record": teams.get("away", {}).get("record", {}).get("leagueRecord", {}),
        "home_record": teams.get("home", {}).get("record", {}).get("leagueRecord", {})
    }

def parse_plays(data):
    """
    Extract play-by-play data and track the final score.
    """
    plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    parsed_plays = []
    
    final_away_score = 0
    final_home_score = 0
    
    for play in plays:
        description = play.get('result', {}).get('description', '')
        inning = play.get('about', {}).get('inning', '')
        
        # Update the score from the current play
        if 'awayScore' in play.get('result', {}):
            final_away_score = play['result']['awayScore']
        if 'homeScore' in play.get('result', {}):
            final_home_score = play['result']['homeScore']
        
        parsed_plays.append(f"Inning {inning}: {description}")
    
    # Add final score to the end of the parsed plays
    final_score = f"Final Score: Away Team {final_away_score} - Home Team {final_home_score}"
    parsed_plays.append(final_score)
    
    return parsed_plays

def generate_game_summary(metadata, game_details, plays):
    """
    Generate a summary of the game details, play-by-play data, boxscore, and player statistics
    as a string instead of printing directly.

    :param metadata: Dictionary containing metadata about the game.
    :param game_details: Dictionary with details about the game (e.g., status, teams).
    :param plays: List of play-by-play data strings.
    :param boxscore: List of team-level boxscore stats, if available.
    :param player_stats: List of player statistics, if available.
    :return: A string containing the game summary.
    """
    summary = []
    
    summary.append("=== Game Summary ===")
    summary.append(f"Timestamp: {metadata['timestamp']}")
    summary.append(f"Game Status: {game_details['status']}")
    summary.append(f"Game Date and Time: {game_details['datetime']}")
    summary.append(f"Away Team: {game_details['away_team']} - "
                   f"Record: {game_details['away_record'].get('wins', 'N/A')} Wins - "
                   f"{game_details['away_record'].get('losses', 'N/A')} Losses")
    summary.append(f"Home Team: {game_details['home_team']} - "
                   f"Record: {game_details['home_record'].get('wins', 'N/A')} Wins - "
                   f"{game_details['home_record'].get('losses', 'N/A')} Losses")
    summary.append(f"Game Events: {', '.join(metadata['game_events'])}")
    summary.append(f"Logical Events: {', '.join(metadata['logical_events'])}")
    
    # Add current score to the summary
    current_score = f"Current Score: Away Team {game_details.get('away_score', 'N/A')} - Home Team {game_details.get('home_score', 'N/A')}"
    summary.append(current_score)
    
    summary.append("\n=== Play-by-Play ===")
    for play in plays:
        summary.append(play)
  
    return "\n".join(summary)

# Define route for home page
@app.route('/')
def home():
    return render_template('index.html', games=games)

@app.route('/game_summary', methods=['POST'])
def game_summary():
    selected_game_pk = request.form['game_pk']
    game_data = fetch_game_data(selected_game_pk)

    if game_data:
        metadata = parse_metadata(game_data)
        game_details = parse_game_data(game_data)
        plays = parse_plays(game_data)

    summary = generate_game_summary(metadata, game_details, plays)

    client = OpenAI(organization='org-XSHDmdWyulF3f94ZUfIdFScW')

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "developer", "content": "You are a helpful assistant whose job is to create summaries of Major League Baseball Games based on the information provided to you. Do not use markdown."},
            {"role": "user", "content": summary}
        ]
    )

    refined_summary = completion.choices[0].message.content

    speech_file_path = Path("static/speech.mp3")  # Save audio in the 'static' folder

    # Generate speech using OpenAI's API
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=refined_summary
    )

    # Write the binary audio content to the file
    with open(speech_file_path, "wb") as audio_file:
        audio_file.write(response.content)

    selected_game = next(game for game in games if str(game['game_pk']) == selected_game_pk)
    game_date = selected_game['game_date']
    team_away = selected_game['team_away']
    team_home = selected_game['team_home']
    
    return render_template(
        'index.html',
        games=games,
        selected_game_summary=refined_summary,
        selected_game_date=game_date,
        selected_game_away=team_away,
        selected_game_home=team_home,
        audio_path=speech_file_path.name  # Pass only the file name
    )

if __name__ == '__main__':
    app.run(debug=True)