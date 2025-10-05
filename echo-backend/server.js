// server.js
const express = require('express');
const { S3Client, ListObjectsV2Command, GetObjectCommand } = require('@aws-sdk/client-s3');
const cors = require('cors');
const streamToString = require('./utils').streamToString; // See the helper function below

const app = express();
app.use(cors()); // Enable CORS for all origins (you can restrict this)
app.use(express.json());

const REGION = 'us-west-2';
const BUCKET = 's3-stage-1-bucket-329857347';

// Configure AWS S3 client with credentials securely stored (e.g., env vars)
const s3Client = new S3Client({
  region: REGION,
  credentials: {
    accessKeyId: 'AKIAREVC3BKQMPNQRWUC',
    secretAccessKey: 'qdBrNqThBb5LGD/Z7/114bLdvuiFiV5UB5rH8HDP',
  },
});

app.get('/api/latest-json', async (req, res) => {
  try {
    const listCommand = new ListObjectsV2Command({
      Bucket: BUCKET,
    });
    const listedObjects = await s3Client.send(listCommand);

    if (!listedObjects.Contents || listedObjects.Contents.length === 0) {
      return res.status(404).json({ error: 'No objects found in S3 bucket' });
    }

    // Find latest object
    let latestObject = listedObjects.Contents.reduce((latest, obj) =>
      !latest || new Date(obj.LastModified) > new Date(latest.LastModified)
        ? obj
        : latest,
      null
    );

    if (!latestObject || !latestObject.Key) {
      return res.status(404).json({ error: 'Could not determine latest object key' });
    }

    const getCommand = new GetObjectCommand({
      Bucket: BUCKET,
      Key: latestObject.Key,
    });
    const response = await s3Client.send(getCommand);

    // Convert stream body to string
    const bodyContents = await streamToString(response.Body);

    // Parse JSON
    const parsedJson = JSON.parse(bodyContents);

    // Return JSON data to frontend
    res.json(parsedJson);
  } catch (error) {
    console.error('Error fetching S3 JSON:', error);
    console.error(error)
    console.error("bucket")
    if (error.$metadata) {
        console.log('AWS SDK Metadata:', error.$metadata);
    }
    res.status(500).json({ error: 'Failed to fetch data from S3' });
  }
});

app.get('/api/agentbucket-latest-json', async (req, res) => {
  try {
    const listCommand = new ListObjectsV2Command({
      Bucket: 'agentbucket3', // New bucket name
    });
    const listedObjects = await s3Client.send(listCommand);

    if (!listedObjects.Contents || listedObjects.Contents.length === 0) {
      return res.status(404).json({ error: 'No objects found in S3 bucket agentbucket3' });
    }

    // Find latest object
    let latestObject = listedObjects.Contents.reduce((latest, obj) =>
      !latest || new Date(obj.LastModified) > new Date(latest.LastModified)
        ? obj
        : latest,
      null
    );

    if (!latestObject || !latestObject.Key) {
      return res.status(404).json({ error: 'Could not determine latest object key in agentbucket3' });
    }

    const getCommand = new GetObjectCommand({
      Bucket: 'agentbucket3',
      Key: latestObject.Key,
    });
    const response = await s3Client.send(getCommand);

    // Convert stream body to string
    const bodyContents = await streamToString(response.Body);

    // Parse JSON
    const parsedJson = JSON.parse(bodyContents);

    // Return JSON data to frontend
    res.json(parsedJson);
  } catch (error) {
    console.error('Error fetching S3 JSON from agentbucket3:', error);
    if (error.$metadata) {
        console.log('AWS SDK Metadata:', error.$metadata);
    }
    res.status(500).json({ error: 'Failed to fetch data from S3 (agentbucket3)' });
  }
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
