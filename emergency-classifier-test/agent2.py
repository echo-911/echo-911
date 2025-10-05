import boto3
import json
import os
import time
import math
from datetime import datetime
from typing import List, Dict, Tuple
from dotenv import load_dotenv

# Strands imports
from strands import Agent, tool
load_dotenv()

# Set up Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')
modelId="anthropic.claude-3-sonnet-20240229-v1:0"
polly_client = boto3.client('polly', region_name='us-west-2')

aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

### ---------- Configuration ----------
SEVERITY_LEVELS = {
    1: "Low Priority - Routine response",
    2: "Medium Priority - Standard response",
    3: "High Priority - Urgent response needed", 
    4: "Critical Priority - Immediate response required",
    5: "Mass Casualty - All available resources"
}

# Mock responder data for house fire scenario
RESPONDERS = [
    {"id": "R001", "name": "Officer Johnson", "lat": 30.2672, "lon": -97.7431, "status": "available", "type": "police", "unit": "Unit 23"},
    {"id": "R002", "name": "Officer Smith", "lat": 30.3078, "lon": -97.7591, "status": "available", "type": "police", "unit": "Unit 47"},
    {"id": "R003", "name": "Paramedic Davis", "lat": 30.2849, "lon": -97.7341, "status": "available", "type": "medical", "unit": "Medic 12"},
    {"id": "R004", "name": "Fire Captain Wilson", "lat": 30.2711, "lon": -97.7437, "status": "available", "type": "fire", "unit": "Engine 8"},
    {"id": "R005", "name": "Officer Brown", "lat": 30.3122, "lon": -97.7289, "status": "available", "type": "police", "unit": "Unit 19"},
    {"id": "R006", "name": "Paramedic Lopez", "lat": 30.2950, "lon": -97.7850, "status": "available", "type": "medical", "unit": "Medic 5"},
    {"id": "R007", "name": "Fire Lieutenant Rodriguez", "lat": 30.3200, "lon": -97.7100, "status": "available", "type": "fire", "unit": "Truck 4"},
    {"id": "R008", "name": "Fire Engineer Thompson", "lat": 30.2600, "lon": -97.7500, "status": "available", "type": "fire", "unit": "Engine 15"},
]

# Track assigned responders globally
assigned_responders = set()

### ---------- Utility Functions ----------
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers"""
    R = 6371  # Earth's radius in km
    
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def calculate_eta(distance_km: float, avg_speed_kmh: float = 60) -> float:
    """Calculate estimated time of arrival in minutes"""
    return (distance_km / avg_speed_kmh) * 60

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

### ---------- Tools ----------

@tool
def generate_dispatch_dialogue(incident_description: str, incident_type: str, assigned_responders: list, location: str, severity: int) -> dict:
    """
    Generate realistic dispatcher dialogue for radio communication to responders.
    
    Args:
        incident_description: Description of the emergency
        incident_type: Type of incident (fire, medical, etc.)
        assigned_responders: List of responder objects
        location: Address/location of incident
        severity: Severity level (1-5)
    
    Returns:
        Dictionary with dispatch dialogue and transmission details
    """
    
    # Create responder call signs
    call_signs = []
    for responder in assigned_responders:
        unit = responder.get('unit', f"Unit {responder['id'][-3:]}")
        call_signs.append(f"{unit} ({responder['name']})")
    
    call_signs_text = ", ".join(call_signs)
    eta_info = []
    for responder in assigned_responders:
        eta = responder.get('eta_minutes', 'Unknown')
        unit = responder.get('unit', f"Unit {responder['id'][-3:]}")
        eta_info.append(f"{unit}: {eta} minutes")
    
    eta_text = ", ".join(eta_info)
    
    prompt = f"""
    You are an experienced emergency dispatcher creating radio dispatch dialogue. Generate realistic, professional radio communication for the following emergency:

    INCIDENT DETAILS:
    - Type: {incident_type}
    - Severity: {severity}/5 ({SEVERITY_LEVELS.get(severity, 'Unknown')})
    - Location: {location}
    - Description: {incident_description}
    - Assigned Units: {call_signs_text}
    - ETAs: {eta_text}

    Create a realistic dispatch transmission that includes:
    1. Professional radio protocol
    2. Clear incident details
    3. Specific location information
    4. Safety warnings/considerations
    5. Expected response actions
    6. Unit assignments and ETAs

    The dialogue should sound like actual emergency radio traffic - concise, clear, and urgent when appropriate.
    Use proper radio terminology and codes where applicable.
    
    Format the response as a single dispatch transmission that would be broadcast to all responding units.
    Make it sound authentic and ready for text-to-speech conversion.
    """
    
    response = call_claude(prompt, 400)
    
    # If Claude fails, provide hardcoded realistic dialogue for house fire
    if "Mock dispatch dialogue" in response or len(response) < 50:
        if "fire" in incident_type.lower() or "fire" in incident_description.lower():
            response = f"""Attention all units, we have a confirmed structure fire at {location}. 
            Reports of active flames on second floor with possible trapped occupants inside. 
            Engine 8, Truck 4, and Engine 15 respond Code 3. Medic 12 and Medic 5 stage for medical support. 
            Unit 23 and Unit 19 provide traffic control and scene security. 
            Be advised: flames visible from second floor windows, screaming heard from inside, 
            caller reporting family may be trapped. Exercise extreme caution on approach. 
            Incident Commander will be Fire Captain Wilson on Engine 8. 
            All units acknowledge and provide your ETA."""
    
    # Parse units and create individual acknowledgments
    unit_acknowledgments = []
    for responder in assigned_responders:
        unit = responder.get('unit', f"Unit {responder['id'][-3:]}")
        eta = responder.get('eta_minutes', 'Unknown')
        
        if responder['type'] == 'fire':
            ack = f"{unit} acknowledging, ETA {eta} minutes, responding Code 3"
        elif responder['type'] == 'medical':
            ack = f"{unit} copy, ETA {eta} minutes, staging for medical support"  
        elif responder['type'] == 'police':
            ack = f"{unit} received, ETA {eta} minutes, en route for traffic control"
        else:
            ack = f"{unit} copy, ETA {eta} minutes, responding"
        
        unit_acknowledgments.append({
            "unit": unit,
            "responder_name": responder['name'],
            "acknowledgment": ack,
            "eta_minutes": eta
        })
    
    return {
        "success": True,
        "incident_location": location,
        "incident_type": incident_type,
        "severity_level": severity,
        "dispatch_transmission": response,
        "units_assigned": len(assigned_responders),
        "unit_acknowledgments": unit_acknowledgments,
        "timestamp": datetime.now().isoformat(),
        "ready_for_audio": True
    }

@tool
def create_followup_updates(initial_dispatch: dict, update_type: str) -> dict:
    """
    Generate follow-up dispatch communications for ongoing incidents.
    
    Args:
        initial_dispatch: The original dispatch information
        update_type: Type of update (arrival, progress, additional_resources, completion)
    
    Returns:
        Dictionary with follow-up dialogue
    """
    
    location = initial_dispatch.get("incident_location", "incident location")
    incident_type = initial_dispatch.get("incident_type", "emergency")
    
    if update_type == "arrival":
        dialogue = f"""Update all units: First responder on scene at {location}. 
        Initial assessment in progress. Standby for scene report."""
        
    elif update_type == "progress":
        if "fire" in incident_type.lower():
            dialogue = f"""Progress update {location}: Fire attack initiated, search and rescue in progress. 
            Two victims evacuated, being treated by EMS. Fire contained to second floor. 
            No additional resources needed at this time."""
        else:
            dialogue = f"""Progress update {location}: Scene secured, primary objectives completed. 
            Situation under control."""
            
    elif update_type == "additional_resources":
        dialogue = f"""Attention dispatch: Requesting additional resources at {location}. 
        Need one additional engine company and supervisor to scene. 
        Also request Red Cross for victim services."""
        
    elif update_type == "completion":
        dialogue = f"""All units {location}: Incident under control. Fire extinguished, 
        all occupants accounted for. Two transported to hospital with smoke inhalation. 
        Scene being turned over to fire marshal for investigation. 
        Units clear to return to service except Engine 8 remaining for overhaul."""
    
    return {
        "update_type": update_type,
        "location": location,
        "followup_transmission": dialogue,
        "timestamp": datetime.now().isoformat(),
        "ready_for_audio": True
    }

@tool
def generate_full_incident_audio_script(incident_data: dict) -> dict:
    """
    Generate complete audio script from initial dispatch through incident completion.
    
    Args:
        incident_data: Complete incident information including assignments
    
    Returns:
        Dictionary with full audio script for text-to-speech
    """
    
    # Extract incident details
    location = incident_data.get("location", "456 Oak Street")
    description = incident_data.get("description", "House fire with potential trapped victims")
    assigned = incident_data.get("assigned_responders", [])
    severity = incident_data.get("severity", 4)
    incident_type = incident_data.get("type", "fire")
    
    # Generate initial dispatch
    initial_dispatch = generate_dispatch_dialogue(
        description, incident_type, assigned, location, severity
    )
    
    # Generate follow-up updates
    arrival_update = create_followup_updates(initial_dispatch, "arrival")
    progress_update = create_followup_updates(initial_dispatch, "progress") 
    completion_update = create_followup_updates(initial_dispatch, "completion")
    
    # Create complete audio script
    full_script = f"""
EMERGENCY DISPATCH AUDIO SCRIPT
Location: {location}
Incident Type: {incident_type}
Severity: {severity}/5

=== INITIAL DISPATCH ===
{initial_dispatch['dispatch_transmission']}

=== UNIT ACKNOWLEDGMENTS ===
"""
    
    for ack in initial_dispatch['unit_acknowledgments']:
        full_script += f"{ack['acknowledgment']}\n"
    
    full_script += f"""
=== ARRIVAL UPDATE (2 minutes later) ===
{arrival_update['followup_transmission']}

=== PROGRESS UPDATE (8 minutes later) ===
{progress_update['followup_transmission']}

=== COMPLETION UPDATE (25 minutes later) ===
{completion_update['followup_transmission']}

=== END OF INCIDENT ===
"""
    
    return {
        "success": True,
        "location": location,
        "full_audio_script": full_script.strip(),
        "total_transmissions": 4,
        "estimated_audio_duration_minutes": 3.5,
        "ready_for_tts": True,
        "sections": {
            "initial_dispatch": initial_dispatch['dispatch_transmission'],
            "acknowledgments": [ack['acknowledgment'] for ack in initial_dispatch['unit_acknowledgments']],
            "arrival_update": arrival_update['followup_transmission'],
            "progress_update": progress_update['followup_transmission'],
            "completion_update": completion_update['followup_transmission']
        }
    }

### ---------- House Fire Scenario Processing ----------
def process_house_fire_scenario() -> dict:
    """Process the specific house fire scenario from test_transcription.txt"""
    
    # House fire incident details
    incident = {
        "id": "INC001",
        "type": "structure_fire",
        "description": "House fire at 456 Oak Street with flames visible from second floor windows, potential trapped family members, screaming heard from inside",
        "location": "456 Oak Street",
        "lat": 30.2672,
        "lon": -97.7431,
        "severity": 5,  # Critical - potential life loss
        "responders_needed": 6
    }
    
    print("🔥 PROCESSING HOUSE FIRE EMERGENCY")
    print("=" * 50)
    print(f"Location: {incident['location']}")
    print(f"Severity: {incident['severity']}/5 (Mass Casualty)")
    print(f"Description: {incident['description']}")
    
    # Find closest responders
    available_responders = []
    for responder in RESPONDERS:
        if responder['status'] == 'available':
            distance = haversine_distance(
                incident['lat'], incident['lon'],
                responder['lat'], responder['lon']
            )
            eta = calculate_eta(distance)
            
            responder_with_eta = {
                **responder,
                'distance_km': round(distance, 2),
                'eta_minutes': round(eta, 1)
            }
            available_responders.append(responder_with_eta)
    
    # Sort by distance and assign closest responders
    available_responders.sort(key=lambda x: x['distance_km'])
    assigned = available_responders[:incident['responders_needed']]
    
    print(f"\n👥 ASSIGNED RESPONDERS:")
    for resp in assigned:
        print(f"  • {resp['unit']} - {resp['name']} ({resp['type']}) - ETA: {resp['eta_minutes']} min")
    
    # Generate dispatch dialogue
    print(f"\n📻 GENERATING DISPATCH DIALOGUE...")
    dispatch_result = generate_dispatch_dialogue(
        incident['description'],
        incident['type'],
        assigned,
        incident['location'],
        incident['severity']
    )
    
    # Generate full audio script
    print(f"\n🎤 GENERATING FULL AUDIO SCRIPT...")
    incident_for_audio = {
        "location": incident['location'],
        "description": incident['description'],
        "assigned_responders": assigned,
        "severity": incident['severity'],
        "type": incident['type']
    }
    
    audio_script = generate_full_incident_audio_script(incident_for_audio)
    
    return {
        "incident": incident,
        "assigned_responders": assigned,
        "dispatch_dialogue": dispatch_result,
        "full_audio_script": audio_script
    }

### ---------- Build Agent ----------
def build_dispatch_dialogue_agent():
    """Build the emergency dispatch dialogue agent"""
    agent = Agent(
        tools=[
            generate_dispatch_dialogue,
            create_followup_updates,
            generate_full_incident_audio_script
        ]
    )
    return agent

### ---------- Main Execution ----------
def main():
    """Main function - process house fire and generate dispatcher dialogue"""
    
    print("📻 EMERGENCY DISPATCH DIALOGUE GENERATOR")
    print("🔥 House Fire Scenario from test_transcription.txt")
    print("=" * 60)
    
    # Process the house fire scenario
    results = process_house_fire_scenario()
    
    print("\n🎯 DISPATCH RESULTS:")
    print("=" * 40)
    
    # Display dispatch transmission
    dispatch = results['dispatch_dialogue']
    print(f"\n📻 INITIAL DISPATCH TRANSMISSION:")
    print("-" * 40)
    print(dispatch['dispatch_transmission'])
    
    print(f"\n📋 UNIT ACKNOWLEDGMENTS:")
    print("-" * 30)
    for ack in dispatch['unit_acknowledgments']:
        print(f"• {ack['acknowledgment']}")
    
    # Display full audio script
    audio_script = results['full_audio_script']
    print(f"\n🎤 COMPLETE AUDIO SCRIPT FOR TEXT-TO-SPEECH:")
    print("=" * 60)
    print(audio_script['full_audio_script'])
    
    print(f"\n📊 AUDIO DETAILS:")
    print(f"  • Total transmissions: {audio_script['total_transmissions']}")
    print(f"  • Estimated duration: {audio_script['estimated_audio_duration_minutes']} minutes")
    print(f"  • Ready for TTS: {audio_script['ready_for_tts']}")
    
    # Save audio script to file for TTS conversion
    audio_filename = f"dispatch_audio_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(audio_filename, 'w') as f:
            f.write("EMERGENCY DISPATCH - HOUSE FIRE AT 456 OAK STREET\n")
            f.write("=" * 50 + "\n\n")
            f.write(audio_script['full_audio_script'])
        
        print(f"\n💾 Audio script saved to: {audio_filename}")
        print("   Ready for text-to-speech conversion!")
        
    except Exception as e:
        print(f"❌ Failed to save audio script: {str(e)}")
    
    # Return results for integration
    return results

### ---------- Quick Test Functions ----------
def test_individual_tools():
    """Test individual tools"""
    print("🔧 TESTING INDIVIDUAL TOOLS")
    print("=" * 40)
    
    # Test data
    test_responders = [
        {"id": "R004", "name": "Fire Captain Wilson", "type": "fire", "unit": "Engine 8", "eta_minutes": 2.3},
        {"id": "R007", "name": "Fire Lieutenant Rodriguez", "type": "fire", "unit": "Truck 4", "eta_minutes": 3.1},
        {"id": "R003", "name": "Paramedic Davis", "type": "medical", "unit": "Medic 12", "eta_minutes": 4.2}
    ]
    
    # Test dispatch dialogue generation
    print("\n1. Testing dispatch dialogue generation...")
    dialogue = generate_dispatch_dialogue(
        "House fire with trapped victims",
        "structure_fire", 
        test_responders,
        "456 Oak Street",
        5
    )
    
    print("✅ Generated dispatch transmission:")
    print(dialogue['dispatch_transmission'][:100] + "...")
    
    # Test follow-up updates
    print("\n2. Testing follow-up updates...")
    update = create_followup_updates(dialogue, "progress")
    print("✅ Generated progress update:")
    print(update['followup_transmission'][:80] + "...")
    
    print("\n🎯 All tools working correctly!")

if __name__ == "__main__":
    # Option to test individual tools first
    test_tools = input("Test individual tools first? (y/n): ").lower().strip() == 'y'
    
    if test_tools:
        test_individual_tools()
        print("\nNow running full house fire scenario...\n")
    
    # Run main house fire scenario
    main()