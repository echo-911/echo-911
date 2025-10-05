#!/usr/bin/env python3

from emergency_classifier import EmergencyClassifier
import json
import sys

def main():
    # Initialize the classifier
    classifier = EmergencyClassifier()
    
    # Example usage
    if len(sys.argv) > 1:
        # Process file from command line argument
        file_path = sys.argv[1]
        print(f"Processing transcription file: {file_path}")
        
        result = classifier.process_transcription_file(file_path)
        
        print("\n" + "="*50)
        print("CLASSIFICATION RESULT")
        print("="*50)
        print(f"Call ID: {result['call_id']}")
        print(f"Primary Type: {result['classification']['primary_type']}")
        print(f"Secondary Types: {', '.join(result['classification']['secondary_types']) if result['classification']['secondary_types'] else 'None'}")
        print(f"Explanation: {result['classification']['explanation']}")
        print(f"Confidence: {result['classification']['confidence_score']:.2f}")
        print(f"\nSeverity Level: {result['severity_level']} - {result['severity_description']}")
        print(f"\nResources Required:")
        for resource in result['resources_required']:
            print(f"  - {resource}")
        print(f"\nTimestamp: {result['timestamp']}")
        
    else:
        # Interactive mode - test with sample transcription
        sample_transcription = """
        911 Operator: 911, what's your emergency?
        Caller: Hi, I need an ambulance at 123 Main Street. My husband is having chest pain and difficulty breathing.
        911 Operator: I'm sending help now. Is he conscious?
        Caller: Yes, but he's sweating a lot and says the pain is really bad.
        911 Operator: How old is your husband?
        Caller: He's 58 years old.
        """
        
        print("Testing with sample transcription...")
        result = classifier.classify_emergency(sample_transcription)
        
        print("\n" + "="*50)
        print("SAMPLE CLASSIFICATION RESULT")
        print("="*50)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()