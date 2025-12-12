# **ECHO-911: A 911 Operator’s Favorite Assistant**

## 🎯 **Project Description**

ECHO-911 is an AWS-powered Operator Assistant designed to enhance emergency response efficiency. By transcribing incoming 911 calls and extracting additional information 
that could be useful while answering a call, the program allows the operator to easily understand what their caller is saying along with other factors such as 
the weather and environment of their location. This program also dynamically assigns dispatchers based off of their proximity to the event and the urgency of each 
situation. Each dispatcher gets a set of instructions and policies that they should follow while handling this emergency. 


## 👩🏽‍💻 **Setup and Installation**
* How to start the server: navigate to echo-backend and in the terminal run "node server.js"
* How to start the webapp: navigate to echo-911/frontend_dashboard/dashboard_new and in the terminal run "npm run start"
* How to view the results of each individual agent: navigate to echo-911/emergency-classifier-test and run "python3 [agentName].py"
* To install depedencies for the agents : run the command "pip install -r requirements.txt"

## 🏗️ **AWS Tools & Services Used**

1. AWS Connect in order to recieve the call
2. AWS Transcribe + Comprehend to transcribe the call 
3. S3 storage to store the transcriptions + agent responses 
4. External APIS: OpenStreetMap API, Open-Meteo API, and Claude Sonnet to grab weather data + build the agent 
5. Amazon Bedrock
6. AWS Strands to connect the tools and agents
7. AWS Polly
8. AWS Lambda 
