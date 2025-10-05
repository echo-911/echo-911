# Define your custom severity levels and resource mappings
SEVERITY_LEVELS = {
    1: "Low Priority",
    2: "Medium Priority", 
    3: "High Priority",
    4: "Critical Priority",
    5: "Mass Casualty/Major Emergency"
}

# Define what resources are needed for different emergency types
RESOURCE_MAPPING = {
    # Medical Emergencies
    "medical_cardiac": {
        "resources": ["Paramedics", "ALS Ambulance", "Fire Department"],
        "default_severity": 4
    },
    "medical_trauma": {
        "resources": ["Paramedics", "ALS Ambulance", "Fire Department", "Police"],
        "default_severity": 4
    },
    "medical_overdose": {
        "resources": ["Paramedics", "ALS Ambulance", "Police"],
        "default_severity": 3
    },
    "medical_general": {
        "resources": ["EMT", "BLS Ambulance"],
        "default_severity": 2
    },
    
    # Fire Emergencies
    "fire_structure": {
        "resources": ["Fire Department", "Ladder Truck", "Engine Company", "Battalion Chief", "Paramedics"],
        "default_severity": 5
    },
    "fire_vehicle": {
        "resources": ["Fire Department", "Engine Company", "Police"],
        "default_severity": 3
    },
    "fire_wildland": {
        "resources": ["Fire Department", "Wildland Units", "Air Support", "Battalion Chief"],
        "default_severity": 4
    },
    
    # Police Emergencies
    "police_violent_crime": {
        "resources": ["Police", "Supervisor", "K9 Unit", "Paramedics"],
        "default_severity": 4
    },
    "police_domestic": {
        "resources": ["Police", "Supervisor", "Paramedics"],
        "default_severity": 3
    },
    "police_traffic": {
        "resources": ["Police", "Traffic Unit"],
        "default_severity": 2
    },
    "police_burglary": {
        "resources": ["Police", "Detective"],
        "default_severity": 2
    },
    
    # Multi-Agency
    "accident_major": {
        "resources": ["Police", "Fire Department", "Paramedics", "Traffic Control"],
        "default_severity": 4
    },
    "accident_minor": {
        "resources": ["Police", "EMT"],
        "default_severity": 2
    },
    "hazmat": {
        "resources": ["Fire Department", "Hazmat Team", "Police", "Public Health", "Environmental"],
        "default_severity": 5
    }
}