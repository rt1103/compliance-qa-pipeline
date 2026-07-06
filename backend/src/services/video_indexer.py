import os
import time
import logging
import requests
import yt_dlp  #helps to download videos from YouTube and other platforms
from azure.identity import DefaultAzureCredential #this is used to authenticate with Azure services using the default credentials available in the environment

logger = logging.getLogger("video-indexer")

class VideoIndexerService:

    #this is the constructor method that initializes the VideoIndexerService class with necessary Azure credentials and configuration parameters. It retrieves these values from environment variables.
    def __init__(self):
        self.account_id = os.getenv("AZURE_VI_ACCOUNT_ID")
        self.location = os.getenv("AZURE_VI_LOCATION")
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = os.getenv("AZURE_RESOURCE_GROUP")
        self.vi_name = os.getenv("AZURE_VI_NAME", "project-brand-guardian-001")
        self.credential = DefaultAzureCredential()

  #this method generates an Azure Resource Manager (ARM) access token, which is required to authenticate API requests to Azure services. It uses the DefaultAzureCredential to obtain the token for the management.azure.com scope. If it fails, it logs an error and raises an exception.
  #basically  are creating a security layer between vs code and azure application so that only authorized users can access the application and its resources.
    def get_access_token(self):
        """Generates an ARM Access Token."""
        try:
            token_object = self.credential.get_token("https://management.azure.com/.default")
            return token_object.token
        except Exception as e:
            logger.error(f"Failed to get Azure Token: {e}")
            raise


    def get_account_token(self, arm_access_token):
        """Exchanges ARM token for Video Indexer Sandbox/Trial Account Token."""
        
        # ONLY the URL string inside changed to match the trial setup
        url = (
            f"https://management.azure.com/providers/Microsoft.VideoIndexer"
            f"/accounts/{self.vi_name}/generateAccessToken?api-version=2024-01-01"
        )
        headers = {"Authorization": f"Bearer {arm_access_token}"}
        payload = {"permissionType": "Contributor", "scope": "Account"}
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"Failed to get VI Account Token: {response.text}")
        return response.json().get("accessToken") #this line extracts the access token from the JSON response returned by the Azure Video Indexer API. The access token is needed for subsequent API calls to perform operations like uploading videos and retrieving insights.


    # --- NEW FUNCTION: Download from YouTube ---
    def download_youtube_video(self, url, output_path="temp_video.mp4"):
        """Downloads a YouTube video to a local file."""
        logger.info(f"Downloading YouTube video: {url}")
        
        ydl_opts = {
         'format': 'best',       #Download the BEST quality available
         'outtmpl': output_path, #Save the file at the given path e.g. "temp_video.mp4"
         'quiet': False,         #Show download progress in terminal  (don't stay silent)
         'no_warnings': False,   #Show warnings if anything goes wrong (don't hide problems)
    # Add these options:
         'extractor_args': {'youtube': {'player_client': ['android', 'web']}}, # → Try to download as if you're an Android app or Web browser  (bypasses some YouTube restrictions)
         'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' # retend to be a real Windows browser (so YouTube doesn't block the request)
    }

}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Download complete.")
            return output_path
        except Exception as e:
            raise Exception(f"YouTube Download Failed: {str(e)}")


    # --- UPDATED FUNCTION: Upload Local File ---
    def upload_video(self, video_path, video_name):
        """Uploads a LOCAL FILE to Azure Video Indexer."""
        arm_token = self.get_access_token()
        vi_token = self.get_account_token(arm_token)

        api_url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos"  #this is basically the endpoint for uploading videos to Azure Video Indexer. It includes the location and account ID to specify which Azure Video Indexer account to use.
        
        params = {
            "accessToken": vi_token,
            "name": video_name,
            "privacy": "Private",
            "indexingPreset": "Default",
            # We removed "videoUrl" because we are sending a file payload instead
        }
        
        logger.info(f"Uploading file {video_path} to Azure...")
        
        # Open the file in binary mode and stream it to Azure
        with open(video_path, 'rb') as video_file:
            files = {'file': video_file}
            response = requests.post(api_url, params=params, files=files)
        
        if response.status_code != 200:
            raise Exception(f"Azure Upload Failed: {response.text}")
            
        return response.json().get("id")


    def wait_for_processing(self, video_id):
        """Polls status until complete."""
        logger.info(f"Waiting for video {video_id} to process...")
        while True:
            arm_token = self.get_access_token()
            vi_token = self.get_account_token(arm_token)
            
            url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos/{video_id}/Index"
            params = {"accessToken": vi_token}
            response = requests.get(url, params=params)
            data = response.json()
            
            state = data.get("state")
            if state == "Processed":
                return data
            elif state == "Failed":
                raise Exception("Video Indexing Failed in Azure.")
            elif state == "Quarantined":
                raise Exception("Video Quarantined (Copyright/Content Policy Violation).")
            
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