import requests

API_KEY = 'AIzaSyC3gBda6Qo6keCUBcJ7bkG1bfUlyJSTTHU'
search_query = 'Python programming'
url = f'https://www.googleapis.com/youtube/v3/search?part=snippet&q={search_query}&key={API_KEY}'

response = requests.get(url)
data = response.json()

for item in data['items']:
    video_id = item['id'].get('videoId')
    if video_id:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(video_url)
