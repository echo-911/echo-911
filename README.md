# **ECHO-911: A 911 Operator’s Favorite Assistant**

## 🎯 **Project Description**

ECHO-911 is an AWS-powered Operator Assistant designed to enhance emergency response efficiency. By transcribing incoming 911 calls and extracting additional information that could be useful while answering a call, the program allows the operator to easily understand what their caller is saying along with other factors such as the weather and environment of their location. This program also dynamically assigns dispatchers based off of their proximity to the event and the urgency of each situation. Each dispatcher gets a set of instructions and policies that they should follow while handling this emergency. This automated process significantly reduces the amount of time required to resolve a 911 emergency. 


## 👩🏽‍💻 **Setup and Installation**
* How to start the server: navigate to echo-backend and in the terminal run "node server.js"
* How to start the webapp: navigate to echo-911/echo-frontend and in the terminal run "npm run start"
* How to view the results of each individual agent: navigate to echo-911/emergency-classifier-test and run "python3 [agentName].py"
* To install depedencies for the agents : run the command "pip install -r requirements.txt"

## 🏗️ **AWS Tools & Services Used**

1. AWS Connect in order to recieve the call
2. AWS Transcribe + Comprehend to transcribe the call 
3. S3 storage to store the transcriptions + agent responses 
4. External APIS: OpenStreetMap API and Open-Meteo APIto grab weather data
5. Amazon Bedrock to access and run the Claude Sonnet model
6. AWS Strands to connect the tools and agents
7. AWS Polly to convert the agent responses back into speech 
8. AWS Lambda to handle the backend logic and extract key features from the call as soon as it starts

## **In Conclusion ... **
ECHO-911 is a next-generation network assistant for 911 operators—breaking barriers, not replacing the human touch. We're so thankful to AWS, At&T, Deloitte, and SMU for giving us the opportunity to participate in this hackathon and get hands-on experience with these tools. We can't wait to see where this project goes in the future and thank you for awarding us with the 1st place prize!
