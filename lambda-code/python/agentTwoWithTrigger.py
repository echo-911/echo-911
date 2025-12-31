import json
import boto3
import os
import time
import math
import shutil
import urllib.parse
from datetime import datetime
from typing import List, Dict, Tuple
# from dotenv import load_dotenv  <-- Not needed in Lambda (use Env Vars)
# from pathlib import Path        <-- Not needed for Lambda logic
# from strands import Agent, tool <-- Removed to simplify Lambda deployment (logic is sequential)

# load_dotenv(...) <-- logic handled by AWS Lambda Environment Variables

# Initialize Clients Globally for Lambda Warm Starts
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')
polly_client = boto3.client('polly', region_name='us-west-2')

# Existing agentTwo-dispatcher.py RESPONDERS data (Exact copy)
RESPONDERS = [
    {"id": "R001", "name": "Officer Johnson", "lat": 30.2672, "lon": -97.7431, "status": "available", "type": "police", "unit": "Unit 23"},
    {"id": "R002", "name": "Officer Smith", "lat": 30.3078, "lon": -97.7591, "status": "available", "type": "police", "unit": "Unit 47"},
    {"id": "R003", "name": "Paramedic Davis", "lat": 30.2849, "lon": -97.7341, "status": "available", "type": "medical", "unit": "Medic 12"},
    {"id": "R004", "name": "Fire Captain Wilson", "lat": 30.2711, "lon": -97.7437, "status": "available", "type": "fire", "unit": "Engine 8"},
    {"id": "R005", "name": "Officer Brown", "lat": 30.3122, "lon": -97.7289, "status": "available", "type": "police", "unit": "Unit 19"},
    {"id": "R006", "name": "Paramedic Lopez", "lat": 30.2950, "lon": -97.7850, "status": "available", "type": "medical", "unit": "Medic 5"},
    {"id": "R007", "name": "Fire Lieutenant Rodriguez", "lat": 30.3200, "lon": -97.7100, "status": "available", "type": "fire", "unit": "Truck 4"},
    {"id": "R008", "name": "Fire Engineer Thompson", "lat": 30.2600, "lon": -97.7500, "status": "available", "type": "fire", "unit": "Engine 15"}
]

SEVERITYLEVELS = {
    1: "Low Priority - Routine response",
    2: "Medium Priority - Standard response", 
    3: "High Priority - Urgent response needed",
    4: "Critical Priority - Immediate response required",
    5: "Mass Casualty - All available resources"
}

def call_claude(prompt: str, max_tokens: int = 500) -> str:
    """Make a call to Claude via Bedrock"""
    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        response = bedrock_runtime.invoke_model(
            body=json.dumps(body),
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text'].strip()
        
    except Exception as e:
        print(f"DEBUG: Claude API Error: {str(e)}")
        return "Mock dispatch dialogue - API unavailable"

# Existing utility functions from agentTwo-dispatcher.py
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def calculate_eta(distance_km: float, avg_speed_kmh: float = 60) -> float:
    return distance_km / avg_speed_kmh * 60

# @tool  <-- Removed for Lambda (function called directly)
def llm_classify_incident(agent1_data: Dict) -> Dict:
    """
    Use LLM to classify incident type, severity, and responder needs from agent1 output.
    """
    address = agent1_data.get("address", "Unknown location")
    coords = agent1_data.get("coordinates", {}) or {}
    lat = coords.get("lat", 30.2672)
    lon = coords.get("lon", -97.7431)
    callinfo = agent1_data.get("call_info", {}) or {}

    summary = callinfo.get("Summary", "Emergency call")
    additional_info = callinfo.get("AdditionalInfo", [])
    threat_level = callinfo.get("ThreatLevel", "Unknown")
    weather = agent1_data.get("weather", {}) or {}
    area_description = agent1_data.get("area_description", "Unknown area")

    context = f"""
EMERGENCY 911 CALL ANALYSIS
Location: {address} (lat:{lat}, lon:{lon})
Summary: {summary}
Additional: {', '.join(additional_info[:3]) if isinstance(additional_info, list) else str(additional_info)}
Weather: {weather}
Area description (truncated): {str(area_description)[:200]}...
ThreatLevel tag from upstream: {threat_level}
"""

    prompt = f"""
You are an expert emergency dispatch supervisor. Analyze this 911 call context:

{context}

Classify the incident and respond with a SINGLE JSON object, no extra text:

{{
  "incident_type": "structurefire|medical|mva|police|hazardous|masscasualty|other",
  "severity": 1|2|3|4|5,
  "reasoning": "2-3 sentences explaining your decision",
  "responders_needed": 2-8,
  "response_types": ["fire","medical","police"]  // one or more of these, no others
}}

Guidelines:
- structurefire: Any building/vehicle/outdoor fire, smoke, or trapped people.
- medical: Medical complaints, unconscious, breathing issues, injuries.
- mva: Motor vehicle collision, rollover, crash.
- masscasualty: More than 3 victims, large-scale events, shootings, explosions.
- severity 5: Imminent life threat, multiple trapped, mass casualty.
- severity 3: Urgent but localized incident.
- responders_needed: Match scale (typical: fire 5-6, medical 2-3, mva 3-4).
- response_types should list ALL services needed, for example:
  - structurefire with injuries → ["fire","medical"]
  - serious crash with traffic control → ["medical","police"]
  - mass casualty event → ["fire","medical","police"]

Return ONLY valid JSON for the object above.
"""

    raw = call_claude(prompt, max_tokens=400)

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        json_str = raw[start:end]
        data = json.loads(json_str)
    except Exception:
        s = summary.lower()
        if "fire" in s:
            data = {
                "incident_type": "structurefire",
                "severity": 4,
                "reasoning": "Fallback: summary contains 'fire', assume critical structure fire.",
                "responders_needed": 6,
                "response_types": ["fire"],
            }
        elif any(k in s for k in ["unconscious", "medical", "heart", "breathing"]):
            data = {
                "incident_type": "medical",
                "severity": 3,
                "reasoning": "Fallback: medical-related keywords in summary.",
                "responders_needed": 3,
                "response_types": ["medical"],
            }
        else:
            data = {
                "incident_type": "other",
                "severity": 2,
                "reasoning": "Fallback: no clear pattern; classify as low/medium priority.",
                "responders_needed": 2,
                "response_types": ["fire","medical","police"],
            }

    # Normalize response_types
    rtypes = data.get("response_types") or []
    if isinstance(rtypes, str):
        rtypes = [rtypes]
    # Keep only allowed and de-duplicate
    allowed = {"fire", "medical", "police"}
    data["response_types"] = list({t for t in rtypes if t in allowed}) or ["fire","medical","police"]

    print("LLM classification:", data)
    return data

def generate_incident_narrative(agent1_data: Dict,
                               incident: Dict,
                               assigned_responders: List[Dict]) -> str:
    address = incident.get("location", "Unknown location")
    incident_type = incident.get("type", "incident")
    severity = incident.get("severity", 0)

    weather = agent1_data.get("weather", {})
    summary = agent1_data.get("call_info", {}).get("Summary", "")
    transcript = agent1_data.get("transcript", "")

    responder_info = []
    for r in assigned_responders:
        responder_info.append(
            f"{r['type']} unit {r['unit']} (~{r['eta_minutes']} min)"
        )

    context = f"""
RAW CALL SUMMARY:
{summary}

INCIDENT TYPE: {incident_type}
SEVERITY: {severity}/5
LOCATION: {address}

RESPONDERS DISPATCHED:
{", ".join(responder_info)}

WEATHER:
{weather}

CALL TRANSCRIPT (truncated):
{str(transcript)[:500]}
"""

    prompt = f"""
You are an emergency dispatch supervisor.

Using the information below, write a concise but vivid
incident narrative suitable for:
- situation reports
- command briefings
- post-incident review

Requirements:
- 4–6 sentences
- Plain professional language
- Describe hazards, life risk, and response status
- Do NOT speculate
- Do NOT include JSON or formatting

{context}
"""

    return call_claude(prompt, max_tokens=250)

def process_incident_from_agent1(agent1_data: Dict, responders: List[Dict], key: str) -> Dict:
    """Process agent1 output to create dispatch-ready incident data using LLM classification."""
    # 1) Ask the LLM to classify the incident
    classification = llm_classify_incident(agent1_data)

    address = agent1_data.get("address", "Unknown location")
    coords = agent1_data.get("coordinates", {}) or {}
    lat = coords.get("lat", 30.2672)
    lon = coords.get("lon", -97.7431)
    summary = agent1_data.get("call_info", {}).get("Summary", "Emergency call")

    # 2) Compute distance and ETA for all available responders
    available = []
    for r in responders:
        if r.get("status") != "available":
            continue
        dist = haversine_distance(lat, lon, r["lat"], r["lon"])
        eta = calculate_eta(dist)
        rr = r.copy()
        rr["distance_km"] = round(dist, 2)
        rr["eta_minutes"] = round(eta, 1)
        available.append(rr)

    # 3) Filter by response_type if LLM requested a specific service
    response_types = classification.get("response_types", "police")
    if response_types:
        available = [r for r in available if r["type"] in response_types]

    available.sort(key=lambda x: x["distance_km"])

    requested = max(1, min(classification.get("responders_needed", 2), len(available)))
    assigned = available[:requested]

    print(f"PROCESSING INCIDENT: {summary}")
    print(f"Location: {address} (lat:{lat}, lon:{lon})")
    print(
        f"LLM decision → type={classification['incident_type']}, "
        f"severity={classification['severity']}, responders_needed={requested}"
    )
    print("Assigned responders:")
    for r in assigned:
        print(f"  {r['unit']} - {r['name']} ({r['type']}) ETA {r['eta_minutes']} min")

    incident = {
        "id": f"INC_{key.split('/')[-1].split('.json')[0]}",
        "type": classification["incident_type"],
        "description": summary,
        "location": address,
        "lat": lat,
        "lon": lon,
        "severity": classification["severity"],
        "response_type": response_types,
        "llm_reasoning": classification.get("reasoning", ""),
    }
    incident_narrative = generate_incident_narrative(
        agent1_data,
        incident,
        assigned
    )
    incident["incident_narrative"] = incident_narrative

    return {
        "incident": incident,
        "assigned_responders": assigned,
        "llm_classification": classification,
        "agent1_data": agent1_data,
    }

# @tool <-- Removed for Lambda
def generate_dispatch_dialogue(
    incident_id: str,
    incident_description: str,
    incident_type: str,
    assigned_responders: list,
    location: str,
    severity: int
) -> dict:
    """
    Generate realistic, concise dispatcher dialogue.
    """
    # Shared incident context for the LLM
    base_context = f"""
INCIDENT DETAILS:
- Type: {incident_type}
- Severity: {severity}/5 ({SEVERITYLEVELS.get(severity, 'Unknown')})
- Location: {location}
- Description: {incident_description}
"""

    # First: one short global broadcast for all units
    global_prompt = f"""
You are an experienced emergency dispatcher.
Using the incident details below, create ONE short initial radio broadcast 
addressed to ALL responding units.

{base_context}

Requirements:
- Professional radio style, clear and concise (3–5 sentences).
- Include: incident type, exact location, severity, obvious hazards, and confirmation that individual assignments will follow.
- Do NOT include per-unit instructions here.

Return ONLY the radio message text.
"""
    global_brief = call_claude(global_prompt, 180)

    responder_scripts = []

    # Then: a short, tailored script for each unit
    for responder in assigned_responders:
        unit = responder.get("unit", f"Unit {responder['id'][-3:]}")
        name = responder.get("name", "Unknown")
        rtype = responder.get("type", "other")
        eta = responder.get("eta_minutes", "Unknown")
        distance_km = responder.get("distance_km", "Unknown")

        role_hint = ""
        if rtype == "fire":
            role_hint = "primary fire suppression, search and rescue, and incident command as appropriate."
        elif rtype == "medical":
            role_hint = "patient triage, treatment, and transport coordination."
        elif rtype == "police":
            role_hint = "traffic control, scene security, perimeter control, and crowd management."
        else:
            role_hint = "supporting operations as directed by the Incident Commander."

        unit_prompt = f"""
You are an emergency dispatcher creating an INDIVIDUAL radio message for a single responding unit.

INCIDENT (shared for all units):
{base_context}

RESPONDER:
- Unit: {unit}
- Name: {name}
- Type: {rtype}
- Estimated distance: {distance_km} km
- ETA: {eta} minutes

Create ONE short, clear radio transmission addressed ONLY to this unit.

Content requirements:
1. Address the unit by call sign (e.g., "{unit}").
2. Briefly restate the incident and exact location.
3. Give this unit specific instructions for their role:
   - Fire: approach route, staging/side of structure, initial actions ({role_hint})
   - Medical: staging location, access route, initial triage/treatment focus.
   - Police: access route, traffic points, perimeter / crowd / scene control.
4. Mention any obvious approach or access hints (e.g., use main entrance, stage in front of address, avoid blocking hydrants).
5. Keep it SHORT and concise (2–4 sentences total), ready for text-to-speech.
6. Use professional radio style, but no 10-codes beyond plain language.

Return ONLY the radio message text, nothing else.
"""

        indiv_script = call_claude(unit_prompt, 220)

        responder_scripts.append({
            "unit": unit,
            "responder_name": name,
            "type": rtype,
            "eta_minutes": eta,
            "script": indiv_script
        })

    return {
        "success": True,
        "incident_number": incident_id,
        "incident_location": location,
        "incident_type": incident_type,
        "severity_level": severity,
        "global_dispatch_brief": global_brief,
        "responder_scripts": responder_scripts,
        "timestamp": datetime.now().isoformat(),
        "ready_for_audio": True
    }

def sanitize_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)[:80]

def synth_text_to_mp3(text: str, voice_id: str, out_path: str) -> bool:
    """Basic Polly text→MP3 helper."""
    try:
        resp = polly_client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice_id,      # e.g. "Gregory" or "Matthew"
        )
        if "AudioStream" not in resp:
            print("Polly: no AudioStream in response")
            return False
        with open(out_path, "wb") as f:
            f.write(resp["AudioStream"].read())
        return True
    except Exception as e:
        print(f"Polly Audio Generation Error for {out_path}: {e}")
        return False

def generate_incident_audio_from_scripts(dispatch_result: Dict,
                                         voice_id: str = "Gregory") -> Dict:
    """
    Given a dispatch_result like the example JSON, generate:
      - one MP3 for global_dispatch_brief
      - one MP3 per responder script
    """

    location = dispatch_result.get("incident_location", "Unknown_Location")
    incident_type = dispatch_result.get("incident_type", "unknown")
    severity = dispatch_result.get("severity_level", 0)
    global_brief = dispatch_result.get("global_dispatch_brief", "")
    responder_scripts: List[Dict] = dispatch_result.get("responder_scripts", [])

    # Build a folder name for this incident
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{incident_type}_{sanitize_filename(location)}_{ts}"
    
    # LAMBDA CHANGE: Use /tmp for file generation
    incident_folder = os.path.join("/tmp/incident_audio", dispatch_result.get("incident_number", base_name))
    
    # Clean up previous run if exists (container reuse)
    if os.path.exists(incident_folder):
        shutil.rmtree(incident_folder)
    os.makedirs(incident_folder, exist_ok=True)

    # 1) Global brief
    global_fname = os.path.join(incident_folder, "global_brief.mp3")
    global_ok = False
    if global_brief:
        global_ok = synth_text_to_mp3(global_brief, voice_id, global_fname)

    # 2) Per-responder files
    responder_files = []
    for r in responder_scripts:
        unit = r.get("unit", "UnknownUnit")
        name = r.get("responder_name", "Unknown")
        script = r.get("script", "")

        safe_unit = sanitize_filename(unit)
        safe_name = sanitize_filename(name)
        fname = os.path.join(
            incident_folder,
            f"{safe_unit}_{safe_name}.mp3"
        )

        ok = False
        if script:
            ok = synth_text_to_mp3(script, voice_id, fname)

        responder_files.append({
            "unit": unit,
            "responder_name": name,
            "path": fname,
            "success": ok
        })

    overall_success = global_ok and all(r["success"] for r in responder_files)

    return {
        "success": overall_success,
        "incident_folder": incident_folder,
        "global_file": global_fname if global_ok else None,
        "responder_files": responder_files,
        "severity": severity,
        "incident_type": incident_type,
        "location": location,
        "timestamp": datetime.now().isoformat()
    }

def upload_folder_to_s3(local_folder_path, prefix="agentTwoOutput"):
    """Upload entire local folder to S3 with same structure"""
    s3_bucket = os.environ.get("S3_BUCKET_NAME") # Lambda env var
    if not s3_bucket:
        print("No S3_BUCKET_NAME env var set")
        return
    
    # Get the parent directory to preserve the incident folder name
    # local_folder_path is something like /tmp/incident_audio/INC123...
    parent_dir = os.path.dirname(local_folder_path) # /tmp/incident_audio
    
    for root, dirs, files in os.walk(local_folder_path):
        for file in files:
            local_file = os.path.join(root, file)
            # Preserve folder structure: e.g. INC123.../global.mp3
            relative_path = os.path.relpath(local_file, parent_dir)
            s3_key = f"{prefix}/{relative_path}".replace(os.sep, '/')
            
            print(f"Uploading {local_file} -> s3://{s3_bucket}/{s3_key}")
            s3_client.upload_file(local_file, s3_bucket, s3_key)
    
    print(f"Uploaded folder '{local_folder_path}' to s3://{s3_bucket}/{prefix}/")

# LAMBDA ENTRY POINT replacing main_pipeline()
def lambda_handler(event, context):
    """Complete pipeline: agent1 → incident processing → dispatch → audio"""
    
    # 1. Parse S3 Event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
    
    # Set the bucket env var for the upload function to use
    os.environ["S3_BUCKET_NAME"] = bucket

    print("🔗 EMERGENCY DISPATCH PIPELINE TRIGGERED")
    print("=" * 60)
    
    # Step 1: Load agent1 output FROM S3
    print(f"📥 Loading agent1 analysis from s3://{bucket}/{key}...")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    agent1_data = json.loads(response['Body'].read().decode('utf-8'))
    
    # Step 2: Process incident and assign responders
    print("\n🚨 Processing incident...")
    incident_results = process_incident_from_agent1(agent1_data, RESPONDERS, key)
    
    # LAMBDA: Save to /tmp
    with open("/tmp/incident_processing_result.json", "w", encoding="utf-8") as f:
        json.dump(incident_results, f, indent=2)
    
    # Step 3: Generate dispatch dialogue
    print("\n📡 Generating dispatch transmission...")
    incident = incident_results['incident']
    assigned = incident_results['assigned_responders']
    
    dispatch_result = generate_dispatch_dialogue(
        incident['id'], incident['description'], incident['type'], 
        assigned, incident['location'], incident['severity']
    )
    # LAMBDA: Save to /tmp
    with open("/tmp/dispatch_dialogue_result.json", "w", encoding="utf-8") as f:
        json.dump(dispatch_result, f, indent=2)
    
    # Step 4: Generate audio files
    print("\n🎵 Generating emergency audio...")
    audio_result = generate_incident_audio_from_scripts(dispatch_result, voice_id="Matthew")
    
    # Step 5: Save complete results
    final_results = {
        'agent1_analysis': agent1_data,
        'incident': incident,
        'assigned_responders': assigned,
        'dispatch_dialogue': dispatch_result,
        'audio_generation': audio_result,
        'timestamp': datetime.now().isoformat()
    }
    
    # LAMBDA: Save to /tmp folder matching the incident ID structure
    incident_id_folder = audio_result['incident_folder'] # e.g., /tmp/incident_audio/INC123
    output_file = os.path.join(incident_id_folder, "complete_dispatch.json")
    
    with open(output_file, 'w') as f:
        json.dump(final_results, f, indent=2, default=str)
    
    # Upload everything
    prefix = "agentTwoOutput"
    upload_folder_to_s3(incident_id_folder, prefix)
    
    print(f"\n✅ PIPELINE COMPLETE!")
    print(f"📄 Results saved: {output_file}")
    if audio_result['success']:
        print(f"🔊 Audio generated: {audio_result['incident_folder']}")
    print(f"🚒 {len(assigned)} units dispatched | Severity: {incident['severity']}")
    
    return {
        "statusCode": 200, 
        "body": json.dumps(f"Dispatch complete. Data in {bucket}/{prefix}/{os.path.basename(incident_id_folder)}")
    }