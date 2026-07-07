import os
import time
import logging
import requests
import yt_dlp

logger = logging.getLogger("video-indexer")

class VideoIndexerService:

    def __init__(self):
        # Initializing only with the values needed for Trial API Key access
        self.account_id = os.getenv("AZURE_VI_ACCOUNT_ID")
        self.location = os.getenv("AZURE_VI_LOCATION")
        self.api_key = os.getenv("AZURE_VI_API_KEY")

    def get_access_token(self):
        # This function is now a stub; we do not use ARM tokens for Trial accounts.
        return None

    def get_account_token(self, arm_access_token=None):
        """Fetches VI token directly using the Trial API Key."""
        if not self.api_key:
            raise Exception("AZURE_VI_API_KEY is missing in .env file!")

        url = f"https://api.videoindexer.ai/Auth/{self.location}/Accounts/{self.account_id}/AccessToken?allowEdit=true"
        
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get Trial Account Token: {response.text}")
            
        return response.text.strip('"')

    def download_youtube_video(self, url, output_path="temp_video.mp4"):
        logger.info(f"Downloading YouTube video: {url}")
        ydl_opts = {
         'format': 'best',
         'outtmpl': output_path,
         'quiet': False,
         'no_warnings': False,
         'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
         'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Download complete.")
            return output_path
        except Exception as e:
            raise Exception(f"YouTube Download Failed: {str(e)}")

    def upload_video(self, video_path, video_name):
        vi_token = self.get_account_token()
        api_url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos"
        
        params = {
            "accessToken": vi_token,
            "name": video_name,
            "privacy": "Private",
            "indexingPreset": "Default",
        }
        
        logger.info(f"Uploading file {video_path} to Azure...")
        with open(video_path, 'rb') as video_file:
            files = {'file': video_file}
            response = requests.post(api_url, params=params, files=files)
        
        if response.status_code != 200:
            raise Exception(f"Azure Upload Failed: {response.text}")
        return response.json().get("id")

    def wait_for_processing(self, video_id):
        logger.info(f"Waiting for video {video_id} to process...")
        while True:
            vi_token = self.get_account_token()
            url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos/{video_id}/Index"
            params = {"accessToken": vi_token}
            response = requests.get(url, params=params)
            data = response.json()
            
            state = data.get("state")
            # Added "Ready" because sometimes the API returns this instead of "Processed"
            if state in ["Processed", "Ready"]:
                return data
            elif state == "Failed":
                raise Exception("Video Indexing Failed in Azure.")
            
            logger.info(f"Status: {state}... waiting 30s")
            time.sleep(30)

    def extract_data(self, vi_json):
        """Parses the JSON into our State format."""
        transcript_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", {}).get("transcript", []):
                transcript_lines.append(insight.get("text"))
        
        ocr_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", {}).get("ocr", []):
                ocr_lines.append(insight.get("text"))
                
        return {
            "transcript": " ".join(transcript_lines),
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration": vi_json.get("summarizedInsights", {}).get("duration", {}).get("seconds"),
                "platform": "youtube"
            }
        }