import os
import json
import boto3
import time
import requests
import concurrent.futures
from datetime import datetime

# Initialize S3 and Bedrock clients globally for re-use across warm starts
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')
session = requests.Session()

# --- Hardcoded Geocoding (Carried over from your agent1.py) ---
def geocode_address(address: str) -> dict:
    hardcoded_addresses = {
        "456 Oak Street": {"lat": 30.2672, "lon": -97.7431, "display_name": "456 Oak Street, Austin, TX 78705"},
        "123 Main Street": {"lat": 30.2650, "lon": -97.7470, "display_name": "123 Main Street, Austin, TX 78701"},
        "701 W 34th St, Austin, TX 78705": {"lat": 30.2951, "lon": -97.7437, "display_name": "701 W 34th St, Austin, TX 78705"}
    }
    addr_lower = address.lower()
    for addr, coords in hardcoded_addresses.items():
        if addr.lower() == addr_lower:
            return coords
    return {"lat": 30.2672, "lon": -97.7431, "display_name": f"{address}, Austin, TX (demo)", "fallback": True}

# --- Core Logic Functions (Adapted from your agent1.py) ---
def get_weather(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": round(lat, 2), "longitude": round(lon, 2), "current_weather": True}
    try:
        r = session.get(url, params=params, timeout=5)
        cw = r.json().get("current_weather", {})
        return {"temperature_c": cw.get("temperature"), "windspeed_m_s": cw.get("windspeed")}
    except:
        return {"error": "weather failed"}

def invoke_claude(prompt: str, max_tokens: int = 400):
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    })
    response = bedrock_client.invoke_model(
        body=body,
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        accept="application/json",
        contentType="application/json"
    )
    return json.loads(response['body'].read())['content'][0]['text'].strip()

def extract_call_info(transcript: str, sentiment: str) -> dict:
    # Severity Logic
    levels = {1: "Low", 2: "Medium", 3: "High", 4: "Critical", 5: "Mass Casualty"}
    t_lower = transcript.lower()
    level = 1
    if "mass casualty" in t_lower: level = 5
    elif "critical" in t_lower or "screaming" in t_lower: level = 4
    elif "fire" in t_lower: level = 3
    
    summary = invoke_claude(f"Summarize this 911 call in one line: {transcript}", 100)
    additional = invoke_claude(f"Extract top 3 key info points for responders from this transcript: {transcript}", 300)
    
    return {
        "Sentiment": sentiment,
        "ThreatLevel": levels[level],
        "Summary": summary,
        "AdditionalInfo": additional.splitlines()[:3]
    }

# --- Lambda Entry Point ---
def lambda_handler(event, context):
    import urllib.parse
    # 1. Get bucket and key from the S3 event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key']) # clean key
    filename = os.path.basename(key)
    
    # Avoid infinite loops: Don't process files in the results folder
    if key.startswith('emergency_agent_results/'):
        return {'status': 'skipped'}

    print(f"Processing new file: s3://{bucket}/{key}")

    # 2. Download and Parse the JSON
    response = s3_client.get_object(Bucket=bucket, Key=key)
    transcription_json = json.loads(response['Body'].read().decode('utf-8'))
    
    # Combine all messages from the "transcript" list into one paragraph
    if "transcript" in transcription_json:
        full_transcript = " ".join([item["message"] for item in transcription_json["transcript"]])
    else:
        # Fallback for your old format just in case
        full_transcript = transcription_json.get("TranscriptText", "")

    # 3. Execute Agent Logic
    start_time = time.time()
    address = "456 Oak Street" # Usually you'd extract this from the JSON
    geo = geocode_address(address)
    
    weather = get_weather(geo['lat'], geo['lon'])
    area_desc = invoke_claude(f"Emergency hazards for: {geo['display_name']}")
    
    call_info = extract_call_info(
        full_transcript,
        transcription_json.get("Sentiment", {}).get("Sentiment", "UNKNOWN")
    )

    # 4. Consolidate Results
    result = {
        "address": geo["display_name"],
        "coordinates": geo,
        "weather": weather,
        "area_description": area_desc,
        "call_info": call_info,
        "processing_time": round(time.time() - start_time, 2),
        "processed_at": datetime.now().isoformat()
    }

    # 5. Save back to S3
    result_key = f"emergency_agent_results/result_{filename}"
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