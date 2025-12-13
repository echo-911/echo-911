import os
import time
import requests
from dotenv import load_dotenv
from pathlib import Path
import concurrent.futures
from functools import lru_cache
import threading
import boto3
import json

# Strands imports
from strands import Agent, tool

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env.local')

# ---------------- Global clients ----------------
_bedrock_client = None
_s3_client = None
_client_lock = threading.Lock()

def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        with _client_lock:
            if _bedrock_client is None:
                _bedrock_client = boto3.client(
                    'bedrock-runtime',
                    region_name=os.getenv('AWS_REGION', 'us-east-1'),
                    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
                )
    return _bedrock_client

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        with _client_lock:
            if _s3_client is None:
                _s3_client = boto3.client(
                    "s3",
                    region_name=os.getenv("AWS_REGION", "us-east-1"),
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
                )
    return _s3_client

# HTTP session
session = requests.Session()
session.headers.update({"User-Agent": "StrandsAgent/1.0 (email@example.com)"})

# ---------------- Tools ----------------
@lru_cache(maxsize=100)
def geocode_address(address: str) -> dict:
    """HACKATHON VERSION: Hardcoded geocoding for reliable demo"""
    hardcoded_addresses = {
        "456 Oak Street": {"lat": 30.2672, "lon": -97.7431, "display_name": "456 Oak Street, Austin, TX 78705"},
        "123 Main Street": {"lat": 30.2650, "lon": -97.7470, "display_name": "123 Main Street, Austin, TX 78701"},
        "789 Elm Avenue": {"lat": 30.2800, "lon": -97.7500, "display_name": "789 Elm Avenue, Austin, TX 78702"},
        "555 Fire Lane": {"lat": 30.2900, "lon": -97.7600, "display_name": "555 Fire Lane, Austin, TX 78703"},
        "701 W 34th St, Austin, TX 78705": {"lat": 30.2951, "lon": -97.7437, "display_name": "701 W 34th St, Austin, TX 78705"}
    }

    for addr, coords in hardcoded_addresses.items():
        if addr.lower() == address.lower():
            return coords
    for addr, coords in hardcoded_addresses.items():
        if any(part.lower() in address.lower() for part in addr.lower().split() if len(part) > 2):
            coords_copy = coords.copy()
            coords_copy["display_name"] = f"{address} (matched to: {coords['display_name']})"
            return coords_copy
    return {"lat": 30.2672, "lon": -97.7431, "display_name": f"{address}, Austin, TX (demo location)", "fallback": True}

@lru_cache(maxsize=50)
def get_weather_cached(lat_rounded: float, lon_rounded: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat_rounded, "longitude": lon_rounded, "current_weather": True}
    try:
        r = session.get(url, params=params, timeout=5)
        r.raise_for_status()
        cw = r.json().get("current_weather", {})
        return {
            "temperature_c": cw.get("temperature"),
            "windspeed_m_s": cw.get("windspeed"),
            "weathercode": cw.get("weathercode"),
            "time_utc": cw.get("time")
        }
    except Exception as e:
        return {"error": f"weather fetch failed: {str(e)}"}

@tool
def get_weather(lat: float, lon: float) -> dict:
    lat_rounded = round(lat, 2)
    lon_rounded = round(lon, 2)
    return get_weather_cached(lat_rounded, lon_rounded)

@lru_cache(maxsize=20)
def describe_area_with_claude_cached(location_name: str, context: str = "general") -> str:
    try:
        bedrock_client = get_bedrock_client()
        if context == "emergency":
            prompt = f"""Please provide emergency response information for this location: {location_name}
Include demographics, terrain, hazards, landmarks, building types. Focus on first responder needs."""
        else:
            prompt = f"Please give me information about this area including demographics and terrain: {location_name}"

        body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]}
        response = bedrock_client.invoke_model(body=json.dumps(body), modelId="anthropic.claude-3-sonnet-20240229-v1:0", accept="application/json", contentType="application/json")
        response_body = json.loads(response['body'].read())
        text = response_body['content'][0]['text']
        return text.strip()
    except Exception as e:
        return f"Area description unavailable: {e}"

@tool
def extract_summary_from_transcript(transcript: str) -> str:
    """Extract a one-line summary from the emergency call transcript"""
    prompt = f"""You are analyzing an emergency 911 call transcript. Provide a single, concise one-line summary (maximum 15 words) that captures the essential emergency and location.

Format: "[Emergency type] at [location]" or "[Emergency type] involving [key detail]"

Examples:
- "Fire at residential building on Elm Street"
- "Medical emergency involving unconscious adult"
- "Vehicle accident with injuries on Highway 35"

Transcript:
\"\"\"
{transcript}
\"\"\"

Provide ONLY the one-line summary, nothing else."""

    try:
        bedrock_client = get_bedrock_client()
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = bedrock_client.invoke_model(
            body=json.dumps(body),
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        response_body = json.loads(response['body'].read())
        summary = response_body['content'][0]['text'].strip()
        # Remove any quotes or extra formatting
        summary = summary.strip('"\'')
        return summary
    except Exception as e:
        return f"Summary extraction failed: {e}"

@tool
def extract_additional_info_llama(transcript: str) -> list:
    prompt = f"""
You are an emergency call analyst. Extract the top 3 key pieces of information from the caller only. Transcript:
\"\"\"
{transcript}
\"\"\"
"""
    try:
        bedrock_client = get_bedrock_client()
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = bedrock_client.invoke_model(body=json.dumps(body), modelId="anthropic.claude-3-sonnet-20240229-v1:0", accept="application/json", contentType="application/json")
        response_body = json.loads(response['body'].read())
        text = response_body['content'][0]['text']
        bullets = [line.strip(" -•") for line in text.splitlines() if line.strip() and not line.lower().startswith("here") and not line.lower().startswith("top")]
        return bullets[1:4]
    except Exception as e:
        return [f"Error extracting additional info: {e}"]

@tool
def describe_area_with_claude(location_name: str, context: str = "general") -> str:
    return describe_area_with_claude_cached(location_name, context)

def fetch_data_parallel(geo_result, emergency_context=False):
    lat, lon = geo_result["lat"], geo_result["lon"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(get_weather, lat, lon)
        context = "emergency" if emergency_context else "general"
        area_future = executor.submit(describe_area_with_claude, geo_result["display_name"], context)
        weather = weather_future.result(timeout=10)
        area_description = area_future.result(timeout=15)
    return weather, area_description

# ---------------- Call info ----------------
SEVERITY_LEVELS = {
    1: "Low Priority - Routine response",
    2: "Medium Priority - Standard response",
    3: "High Priority - Urgent response needed", 
    4: "Critical Priority - Immediate response required",
    5: "Mass Casualty - All available resources"
}

def extract_call_info(call_json: dict) -> dict:
    sentiment = call_json.get("Sentiment", {}).get("Sentiment", "UNKNOWN")
    transcript = call_json.get("TranscriptText", "")

    transcript_lower = transcript.lower()
    if "mass casualty" in transcript_lower or "multiple people" in transcript_lower:
        threat_level = SEVERITY_LEVELS[5]
    elif "critical" in transcript_lower or "immediately" in transcript_lower or "screaming for help" in transcript_lower:
        threat_level = SEVERITY_LEVELS[4]
    elif "urgent" in transcript_lower or "fire" in transcript_lower:
        threat_level = SEVERITY_LEVELS[3]
    elif "medium" in transcript_lower or "minor" in transcript_lower:
        threat_level = SEVERITY_LEVELS[2]
    else:
        threat_level = SEVERITY_LEVELS[1]

    # Extract one-line summary from transcript
    summary = extract_summary_from_transcript(transcript)
    additional_info = extract_additional_info_llama(transcript)
    words = threat_level.split()

    first_two_words = " ".join(words[:2])
    remaining_words = " ".join(words[3:])

    return {
        "Sentiment": sentiment,
        "ThreatLevel": first_two_words,
        "ThreatLevelDescription:": remaining_words,
        "Summary": summary,
        "AdditionalInfo": additional_info
    }

# ---------------- Run ----------------
def run(address: str, emergency_context: bool = False, transcription_json: dict = None):
    start_time = time.time()
    geo = geocode_address(address)
    if "error" in geo:
        return {"error": geo["error"]}
    lat, lon = geo["lat"], geo["lon"]

    try:
        weather, area_description = fetch_data_parallel(geo, emergency_context)
    except concurrent.futures.TimeoutError:
        weather = {"error": "weather request timed out", "fallback": True}
        area_description = "Area description timed out - using generic info"

    result = {
        "address": geo["display_name"],
        "coordinates": {"lat": lat, "lon": lon},
        "weather": weather,
        "area_description": area_description,
        "emergency_context": emergency_context,
        "processing_time": round(time.time() - start_time, 2),
        "status": "success" if not any(item.get("fallback") for item in [geo, weather] if isinstance(item, dict)) else "partial_success_with_fallbacks"
    }

    if transcription_json:
        result["call_info"] = extract_call_info(transcription_json)

    # save result to file
    with open("emergency_agent_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        
    # Upload synchronously instead of using a daemon thread
    if os.getenv("S3_BUCKET_NAME"):
        prefix = "emergency_agent_results" if emergency_context else "agent_results"
        upload_to_s3(result, prefix)

    return result


def upload_to_s3_async(data: dict, prefix: str = "agent_results"):
    try:
        upload_to_s3(data, prefix)
    except Exception as e:
        print(f"Background S3 upload failed: {e}")

def upload_to_s3(data: dict, prefix: str = "agent_results"):
    s3_bucket = os.getenv("S3_BUCKET_NAME")
    if not s3_bucket:
        return
    s3_client = get_s3_client()
    from datetime import datetime
    file_name = f"{prefix}/result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=file_name,
            Body=json.dumps(data),
            ContentType="application/json"
        )
        print(f"Uploaded result to S3: s3://{s3_bucket}/{file_name}")
    except Exception as e:
        print(f"Failed to upload to S3: {e}")

# ---------------- Main ----------------
if __name__ == "__main__":
    emergency_address = "456 Oak Street"

    # Load transcription JSON from file
    json_file_path = "./latest-json.json"  # replace with your actual file name
    with open(json_file_path, "r") as f:
        transcription_json = json.load(f)

    result = run(emergency_address, emergency_context=True, transcription_json=transcription_json)
    print("="*60)
    print("🚨 EMERGENCY RESPONSE AGENT RESULTS 🚨")
    print("="*60)
    print(json.dumps(result, indent=2))