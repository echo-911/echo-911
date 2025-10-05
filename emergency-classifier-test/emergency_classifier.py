import boto3
import json
from typing import Dict, List, Optional
from severity_config import SEVERITY_LEVELS, RESOURCE_MAPPING
import os
from dotenv import load_dotenv

load_dotenv()

class EmergencyClassifier:
    def __init__(self):
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )

        # S3 setup
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')
        self.s3_client = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
    
    def upload_to_s3(self, data: dict, prefix: str = "classifications") -> None: 
        """Upload classification JSON to S3 with timestamped filename"""
        if not self.s3_bucket:
            print("S3_BUCKET_NAME not set, skipping S3 upload.")
            return
        
        from datetime import datetime
        file_name = f"{prefix}/classification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=file_name,
                Body=json.dumps(data),
                ContentType="application/json"
            )
            print(f"Uploaded classification to S3: s3://{self.s3_bucket}/{file_name}")
        except Exception as e:
            print(f"Failed to upload to S3: {str(e)}")
        
    def create_classification_prompt(self, transcription: str) -> str:
        """Create the prompt for Bedrock to classify the emergency"""
        
        available_types = list(RESOURCE_MAPPING.keys())
        
        prompt = f"""
You are an emergency dispatch classifier. Analyze the following 911 call transcription and classify the emergency type.

TRANSCRIPTION:
{transcription}

AVAILABLE EMERGENCY TYPES:
{', '.join(available_types)}

Your task is to:
1. Identify the primary emergency type from the available types listed above
2. Provide a brief explanation of why you chose this classification
3. Identify any secondary emergency types if applicable

Respond ONLY in this JSON format:
{{
    "primary_type": "exact_type_from_list",
    "explanation": "brief explanation of classification reasoning",
    "secondary_types": ["list", "of", "secondary", "types"],
    "confidence_score": 0.95
}}

Be precise and only use the emergency types from the provided list. If none fit exactly, choose the closest match.
"""
        return prompt
    
    def classify_emergency(self, transcription: str) -> Dict:
        """Use Bedrock to classify the emergency and determine resources needed"""
        
        prompt = self.create_classification_prompt(transcription)
        
        # Prepare the request for Claude on Bedrock
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        try:
            # Call Bedrock
            response = self.bedrock_client.invoke_model(
                body=json.dumps(body),
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",  # Using smaller model as requested
                accept="application/json",
                contentType="application/json"
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            classification_text = response_body['content'][0]['text']
            
            # Parse the JSON response from Claude
            classification_data = json.loads(classification_text)
            
            # Get resource requirements based on classification
            resource_info = self._get_resource_requirements(classification_data)

            self.upload_to_s3(resource_info)
            
            return resource_info
            
        except Exception as e:
            print(f"Error in classification: {str(e)}")
            return self._get_default_classification()
    
    def _get_resource_requirements(self, classification_data: Dict) -> Dict:
        """Convert classification to resource requirements"""
        
        primary_type = classification_data.get('primary_type', 'medical_general')
        secondary_types = classification_data.get('secondary_types', [])
        
        # Get resources for primary type
        primary_resources = RESOURCE_MAPPING.get(primary_type, RESOURCE_MAPPING['medical_general'])
        resources_needed = set(primary_resources['resources'])
        base_severity = primary_resources['default_severity']
        
        # Add resources from secondary types
        for secondary_type in secondary_types:
            if secondary_type in RESOURCE_MAPPING:
                secondary_resources = RESOURCE_MAPPING[secondary_type]['resources']
                resources_needed.update(secondary_resources)
                # Use highest severity level
                secondary_severity = RESOURCE_MAPPING[secondary_type]['default_severity']
                base_severity = max(base_severity, secondary_severity)
        
        return {
            "call_id": f"CALL_{hash(str(classification_data)) % 10000:04d}",
            "classification": {
                "primary_type": primary_type,
                "secondary_types": secondary_types,
                "explanation": classification_data.get('explanation', ''),
                "confidence_score": classification_data.get('confidence_score', 0.0)
            },
            "resources_required": list(resources_needed),
            "severity_level": base_severity,
            "severity_description": SEVERITY_LEVELS[base_severity],
            "timestamp": self._get_timestamp()
        }
    
    def _get_default_classification(self) -> Dict:
        """Return default classification if something goes wrong"""
        return {
            "call_id": "CALL_ERROR",
            "classification": {
                "primary_type": "medical_general",
                "secondary_types": [],
                "explanation": "Classification failed - using default",
                "confidence_score": 0.0
            },
            "resources_required": ["EMT", "BLS Ambulance"],
            "severity_level": 2,
            "severity_description": SEVERITY_LEVELS[2],
            "timestamp": self._get_timestamp()
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def process_transcription_file(self, file_path: str) -> Dict:
        """Process a transcription file and return classification"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                transcription = file.read()
            
            # Classify the emergency
            classification_result = self.classify_emergency(transcription)
            
            return classification_result
            
        except Exception as e:
            print(f"Error processing file: {str(e)}")
            return self._get_default_classification()

def main():
    """Main function to test the emergency classifier with test_transcription.txt"""
    # Create test transcription file if it doesn't exist
    test_content = """911 Operator: 911, what's your emergency?
Caller: There's a house fire at 456 Oak Street! The flames are coming out of the windows on the second floor!
911 Operator: Is anyone inside the house?
Caller: I don't know, I think the family might still be inside. I can hear someone screaming for help!
911 Operator: We're sending fire department and paramedics immediately. Are you in a safe location?
Caller: Yes, I'm across the street. But please hurry, the fire is spreading fast!"""
    
    # Write test file
    with open("test_transcription.txt", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    # Initialize classifier and process the test file
    try:
        classifier = EmergencyClassifier()
        print("Processing test_transcription.txt...")
        result = classifier.process_transcription_file("test_transcription.txt")
        
        print("\n" + "="*50)
        print("EMERGENCY CLASSIFICATION RESULTS")
        print("="*50)
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error running classification: {str(e)}")
        print("\nMake sure you have:")
        print("1. AWS credentials configured in .env file")
        print("2. severity_config.py file with SEVERITY_LEVELS and RESOURCE_MAPPING")
        print("3. Required Python packages installed (boto3, python-dotenv)")

if __name__ == "__main__":
    main()