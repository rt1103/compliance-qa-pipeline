import json
import os
import logging
import re  # <--- Added Regex for cleaning
from typing import Dict, Any, List
# --- CHANGE 1: Swapped AzureChatOpenAI for standard ChatOpenAI ---
from langchain_openai import ChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch  #here pdf will get vectorised and will be stored
from langchain_core.prompts import ChatPromptTemplate #to define the prompt structure for LLM
from langchain_core.messages import SystemMessage, HumanMessage

# Import the State schema .
from backend.src.graph.state import VideoAuditState, ComplianceIssue

# Import the Service
from backend.src.services.video_indexer import VideoIndexerService

from backend.src.services.cache_service import init_db, get_cached_video, save_to_cache

# Configure Logger
logger = logging.getLogger("brand-guardian")
logging.basicConfig(level=logging.INFO)

# --- NODE 1: THE INDEXER ---
#function responsible for downloading the video, uploading it to Azure Video Indexer, and extracting insights basically responsible for converting video to text 
def index_video_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Downloads YouTube video, uploads to Azure VI, and extracts insights.
    """
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo") #this line is used to get the video id from the state object, if not present it will use "vid_demo" as default
    
    logger.info(f"--- [Node: Indexer] Processing: {video_url} ---")  #this line is used to log the video url being processed
    
    local_filename = "temp_audit_video.mp4" # this is where video gets downloaded locally before uploading to Azure Video Indexer
    
    try:
        # Initialize SQLite Database Cache
        init_db()

        # Check Cache BEFORE hitting Azure or downloading via yt-dlp
        cached_data = get_cached_video(video_url)
        if cached_data:
            logger.info(f"--- [Node: Indexer] Cache Hit for {video_url}. Bypassing Azure Processing! ---")
            return cached_data

        vi_service = VideoIndexerService()   #instantiating the VideoIndexerService class to use its methods for video processing
        # We are going to use yt-dlp to download the video from Youtube ..yt-dlp is a free, open-source command-line tool that lets you download videos and audio from YouTube and 1000+ other websites.
        # 1. DOWNLOAD
        if "youtube.com" in video_url or "youtu.be" in video_url:
            local_path = vi_service.download_youtube_video(video_url, output_path=local_filename)
        else:
            raise Exception("Please provide a valid YouTube URL for this test.")

        # 2. UPLOAD
        azure_video_id = vi_service.upload_video(local_path, video_name=video_id_input)  # this line uploads the video to Azure Video Indexer and returns the Azure Video ID provided by the service
        logger.info(f"Upload Success. Azure ID: {azure_video_id}")
        
        # 3. CLEANUP
        #once the video is uploaded to Azure Video Indexer, we can delete the local copy to save space
        if os.path.exists(local_path):
            os.remove(local_path)

        # 4. WAIT
        raw_insights = vi_service.wait_for_processing(azure_video_id) 
        
        # 5. EXTRACT
        clean_data = vi_service.extract_data(raw_insights)
        
        # Save to SQLite Database Cache AFTER successful extraction
        save_to_cache(video_url, clean_data)

        logger.info("--- [Node: Indexer] Extraction Complete ---")
        return clean_data

    except Exception as e:
        logger.error(f"Video Indexer Failed: {e}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "transcript": "", 
            "ocr_text": []
        }

 
# --- NODE 2: THE COMPLIANCE AUDITOR ---
#this is the brain node
def audit_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Performs Retrieval-Augmented Generation (RAG) to audit the content.
    """
    logger.info("--- [Node: Auditor] querying Knowledge Base & LLM ---")
    
    transcript = state.get("transcript", "")
    
    if not transcript:
        logger.warning("No transcript available. Skipping Audit.")
        return {
            "final_status": "FAIL",
            "final_report": "Audit skipped because video processing failed (No Transcript)."
        }

    # --- CHANGE 2: Route LLM to GitHub Models using your GITHUB_TOKEN ---
    llm = ChatOpenAI(
        model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
        api_key=os.getenv("GITHUB_TOKEN"),
        base_url="https://models.inference.ai.azure.com",
        temperature=0.0
    )

    # Embeddings stay on Azure (Free Tier)
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )

#this is where u get all your vectors stored  and you can query them for similarity search
    vector_store = AzureSearch(
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        embedding_function=embeddings.embed_query
    )
    
     
    # RAG Retrieval
    ocr_text = state.get("ocr_text", [])
    query_text = f"{transcript} {' '.join(ocr_text)}" #here we are combining the transcript and OCR text to form a single query for the vector store
    docs = vector_store.similarity_search(query_text, k=3)  #performing similarity search on the vector store to retrieve the top 3 relevant documents based on the query_text
    
    retrieved_rules = "\n\n".join([doc.page_content for doc in docs])
    
    # --- UPDATED PROMPT WITH STRICT SCHEMA ---
    system_prompt = f"""
    You are a Senior Brand Compliance Auditor.
    
    OFFICIAL REGULATORY RULES:
    {retrieved_rules}
    
    INSTRUCTIONS:
    1. Analyze the Transcript and OCR text below.
    2. Identify ANY violations of the rules.
    3. Return strictly JSON in the following format:
    
    {{
        "compliance_results": [
            {{
                "category": "Claim Validation",
                "severity": "CRITICAL",
                "description": "Explanation of the violation..."
            }}
        ],
        "status": "FAIL", 
        "final_report": "Summary of findings..."
    }}

    If no violations are found, set "status" to "PASS" and "compliance_results" to [].
    """

    user_message = f"""
    VIDEO METADATA: {state.get('video_metadata', {})}
    TRANSCRIPT: {transcript}
    ON-SCREEN TEXT (OCR): {ocr_text}
    """
   
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ])
        
        # --- FIX: Clean Markdown if present (```json ... ```) ---
        content = response.content
        if "```" in content:
            # Regex to find JSON inside code blocks
            content = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL).group(1) # this line uses regex to extract the JSON content from the LLM response, ignoring any markdown formatting
            
        audit_data = json.loads(content.strip()) #this line parses the cleaned JSON string into a Python dictionary for further processing
        
        return {
            "compliance_results": audit_data.get("compliance_results", []),
            "final_status": audit_data.get("status", "FAIL"), # this line sets the final status to "FAIL" if not provided by the LLM response
            "final_report": audit_data.get("final_report", "No report generated.")
        }

    except Exception as e:
        logger.error(f"System Error in Auditor Node: {str(e)}")
        
        # Safe lookup using standard dict get() to avoid UnboundLocal/NameError
        raw_response = locals().get("response")
        if raw_response and hasattr(raw_response, "content"):
            logger.error(f"Raw LLM Response: {raw_response.content}")
        else:
            logger.error("Raw LLM Response: None (Inference failed before generating response)")
            
        return {
            "errors": [str(e)],
            "final_status": "FAIL"
        }