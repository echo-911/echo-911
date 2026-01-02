import os
import json
import boto3
import time
import requests
import urllib.parse
from datetime import datetime
from functools import lru_cache

# Initialize S3 and Bedrock clients globally for re-use across warm starts
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')
session = requests.Session()

# ---------------- Tools (Updated from local agent1.py) ----------------

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

    addr_lower = address.lower()
    for addr, coords in hardcoded_addresses.items():
        if addr.lower() == addr_lower:
            return coords
            
    # Partial matching logic from local agent1.py
    for addr, coords in hardcoded_addresses.items():
        if any(part.lower() in addr_lower for part in addr.lower().split() if len(part) > 2):
            coords_copy = coords.copy()
            coords_copy["display_name"] = f"{address} (matched to: {coords['display_name']})"
            return coords_copy
            
    return {"lat": 30.2672, "lon": -97.7431, "display_name": f"{address}, Austin, TX (demo location)", "fallback": True}

def get_weather(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": round(lat, 2), "longitude": round(lon, 2), "current_weather": True}
    try:
        r = session.get(url, params=params, timeout=5)
        cw = r.json().get("current_weather", {})
        return {
            "temperature_c": cw.get("temperature"),
            "windspeed_m_s": cw.get("windspeed"),
            "weathercode": cw.get("weathercode")
        }
    except:
        return {"error": "weather failed"}

def describe_area_with_claude(location_name: str, context: str = "emergency") -> str:
    try:
        if context == "emergency":
            prompt = f"Please provide emergency response information for this location: {location_name}\nInclude demographics, terrain, hazards, landmarks, building types. Focus on first responder needs."
        else:
            prompt = f"Please give me information about this area including demographics and terrain: {location_name}"

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]
        })
        response = bedrock_client.invoke_model(
            body=body,
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        return json.loads(response['body'].read())['content'][0]['text'].strip()
    except Exception as e:
        return f"Area description unavailable: {e}"

# ---------------- Call Info Logic (Updated from local agent1.py) ----------------

SEVERITY_LEVELS = {
    1: "Low Priority - Routine response",
    2: "Medium Priority - Standard response",
    3: "High Priority - Urgent response needed", 
    4: "Critical Priority - Immediate response required",
    5: "Mass Casualty - All available resources"
}

def extract_call_info(transcript: str, sentiment: str) -> dict:
    t_lower = transcript.lower()
    # if "mass casualty" in t_lower or "multiple people" in t_lower:
    #     level_text = SEVERITY_LEVELS[5]
    # elif "critical" in t_lower or "immediately" in t_lower or "screaming" in t_lower:
    #     level_text = SEVERITY_LEVELS[4]
    # elif "fire" in t_lower or "urgent" in t_lower:
    #     level_text = SEVERITY_LEVELS[3]
    # elif "medium" in t_lower:
    #     level_text = SEVERITY_LEVELS[2]
    # else:
    #     level_text = SEVERITY_LEVELS[1]
    severity_prompt = (
        f"You are a 911 dispatcher. Analyze the following transcript and assign a severity level based on these criteria:\n"
        f"{json.dumps(SEVERITY_LEVELS, indent=2)}\n\n"
        f"Transcript: {transcript}\n\n"
        f"Reply with ONLY the integer (1-5) corresponding to the level. Do not output any other text."
    )

    # Use the specific Bedrock prompts from local agent1.py
    def invoke_bedrock(p, tokens):
        body = json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": tokens, "messages": [{"role": "user", "content": p}]})
        resp = bedrock_client.invoke_model(body=body, modelId="anthropic.claude-3-sonnet-20240229-v1:0")
        return json.loads(resp['body'].read())['content'][0]['text'].strip()

    summary_prompt = f"Summarize this 911 call in one line (max 15 words) such that it captures the essential emergency and location. \nHere is the transcript: {transcript}"
    info_prompt = (
        f"You are an emergency call analyst. Extract the top 3 key pieces of information "
        f"from the caller. Return ONLY the 3 points, separated by newlines. "
        f"Do not use introductory text, bullet points, or numbering. "
        f"Transcript: {transcript}"
    )
    try:
        level_response = invoke_bedrock(severity_prompt, 10).strip()
        # Filter digits: "Level 3" -> "3"
        digits = ''.join(filter(str.isdigit, level_response))
        level_id = int(digits)
    except (ValueError, TypeError):
        # Fallback if LLM returns garbage or empty string
        level_id = 3  # Default to Medium Priority
    level_text = SEVERITY_LEVELS[level_id]
    threat_level, threat_desc = level_text.split(" - ", 1)
    summary = invoke_bedrock(summary_prompt, 100).strip('"\'')
    additional = invoke_bedrock(info_prompt, 300)
    
    # Clean up bullets as done in local code
    bullets = [line.strip("-• *") for line in additional.splitlines() if line.strip()]

    return {
        "Sentiment": sentiment,
        "ThreatLevel": threat_level,
        "ThreatLevelDescription": threat_desc,
        "Summary": summary,
        "AdditionalInfo": bullets
    }

# ---------------- Lambda Entry Point ----------------

def lambda_handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
    filename = os.path.basename(key)
    
    if key.startswith(os.environ.get("S3_TARGET_FOLDER_NAME")):
        return {'status': 'skipped'}

    # 1. Download and Parse
    response = s3_client.get_object(Bucket=bucket, Key=key)
    transcription_json = json.loads(response['Body'].read().decode('utf-8'))
    
    # Handle the list structure of your new frontend JSON
    if "transcript" in transcription_json:
        full_transcript = " ".join([item["message"] for item in transcription_json["transcript"]])
    else:
        full_transcript = transcription_json.get("TranscriptText", "")

    # 2. Execute Logic
    start_time = time.time()
    address = "456 Oak Street" # Hardcoded for demo as per local script
    geo = geocode_address(address)
    
    weather = get_weather(geo['lat'], geo['lon'])
    area_desc = describe_area_with_claude(geo['display_name'], context="emergency")
    
    call_info = extract_call_info(
        full_transcript,
        transcription_json.get("Sentiment", {}).get("Sentiment", "UNKNOWN")
    )

    # 3. Consolidate Results
    result = {
        "address": geo["display_name"],
        "coordinates": geo,
        "weather": weather,
        "area_description": area_desc,
        "call_info": call_info,
        "processing_time": round(time.time() - start_time, 2),
        "processed_at": datetime.now().isoformat()
    }

    # 4. Save back to S3
    result_key = f"{os.environ.get("S3_TARGET_FOLDER_NAME")}result_{filename}"
    s3_client.put_object(
        Bucket=bucket,
        Key=result_key,
        Body=json.dumps(result),
        ContentType="application/json"
    )

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed and saved to {result_key}')
    }