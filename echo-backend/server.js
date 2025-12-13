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
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env.local') });

// Configure AWS S3 client with credentials securely stored (e.g., env vars)
const s3Client = new S3Client({
  region: REGION,
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
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

app.get('/api/agentbucket3/emergency_agent_results', async (req, res) => {
  try {
    const listCommand = new ListObjectsV2Command({
      Bucket: 'agentbucket3', // New bucket name
      Prefix: 'emergency_agent_results/',
    });
    const listedObjects = await s3Client.send(listCommand);

    if (!listedObjects.Contents || listedObjects.Contents.length === 0) {
      return res.status(404).json({ error: 'No objects found in S3 bucket agentbucket3/emergency_agent_results/' });
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
      Prefix: 'emergency_agent_results/',
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
    console.error('Error fetching S3 JSON from agentbucket3/emergency_agent_results/:', error);
    if (error.$metadata) {
        console.log('AWS SDK Metadata:', error.$metadata);
    }
    res.status(500).json({ error: 'Failed to fetch data from S3 (agentbucket3/emergency_agent_results/)' });
  }
});

// Utility: find latest incident folder under agentTwoOutput/
async function getLatestIncidentPrefix() {
  const listCommand = new ListObjectsV2Command({
    Bucket: 'agentbucket3',
    Prefix: 'agentTwoOutput/',        // where your incidents live
  });

  const listed = await s3Client.send(listCommand);
  if (!listed.Contents || listed.Contents.length === 0) {
    return null;
  }

  // Map each object to its "folder" = first segment after agentTwoOutput/
  const folderMap = new Map(); // folderPrefix -> latest LastModified

  for (const obj of listed.Contents) {
    const key = obj.Key;                  // e.g. "agentTwoOutput/INC1765.../global_brief.mp3"
    const parts = key.split('/');
    if (parts.length < 3) continue;       // skip root objects like "agentTwoOutput/"

    const folderPrefix = `${parts[0]}/${parts[1]}/`; // "agentTwoOutput/INC1765.../"
    const current = folderMap.get(folderPrefix);
    if (!current || obj.LastModified > current) {
      folderMap.set(folderPrefix, obj.LastModified);
    }
  }

  if (folderMap.size === 0) return null;

  // Pick folder with newest LastModified
  let latestFolder = null;
  let latestDate = null;
  for (const [folder, date] of folderMap.entries()) {
    if (!latestDate || date > latestDate) {
      latestDate = date;
      latestFolder = folder;
    }
  }

  return latestFolder; // e.g. "agentTwoOutput/INC1765596766/"
}

app.get('/api/agentbucket3/emergency_agent_results/incident_full_details', async (req, res) => {
  try {
    // 1) Find latest incident folder under agentTwoOutput/
    const latestPrefix = await getLatestIncidentPrefix();
    if (!latestPrefix) {
      return res.status(404).json({ error: 'No incident folders found under agentTwoOutput/' });
    }

    // 2) List all objects in that folder
    const listCommand = new ListObjectsV2Command({
      Bucket: 'agentbucket3',
      Prefix: latestPrefix,             // e.g. "agentTwoOutput/INC1765596766/"
    });
    const listedObjects = await s3Client.send(listCommand);

    if (!listedObjects.Contents || listedObjects.Contents.length === 0) {
      return res.status(404).json({ error: `No objects found in latest incident folder ${latestPrefix}` });
    }

    // 3) Fetch every object in that folder
    const files = [];
    for (const obj of listedObjects.Contents) {
      if (!obj.Key || obj.Key.endsWith('/')) continue; // skip folder placeholder

      const getCommand = new GetObjectCommand({
        Bucket: 'agentbucket3',
        Key: obj.Key,                  // no Prefix field here
      });
      const response = await s3Client.send(getCommand);

      // Decide how to return: JSON as parsed, audio as base64 or leave as is
      const contentType = response.ContentType || 'application/octet-stream';

      let body;
      if (contentType.startsWith('application/json') || obj.Key.endsWith('.json')) {
        const text = await streamToString(response.Body);
        body = JSON.parse(text);
      } else {
        // For mp3s etc. send as base64 so frontend can reconstruct Blob
        const buf = await new Promise((resolve, reject) => {
          const chunks = [];
          response.Body.on('data', (c) => chunks.push(c));
          response.Body.on('error', reject);
          response.Body.on('end', () => resolve(Buffer.concat(chunks)));
        });
        body = buf.toString('base64');
      }

      files.push({
        key: obj.Key,          // full S3 key
        contentType,
        body,                  // JSON object or base64 string
      });
    }

    // 4) Return everything together
    res.json({
      incidentPrefix: latestPrefix,  // e.g. "agentTwoOutput/INC1765596766/"
      files,                         // all JSON + mp3 files from that folder
    });
  } catch (error) {
    console.error('Error fetching latest incident folder from agentTwoOutput:', error);
    if (error.$metadata) {
      console.log('AWS SDK Metadata:', error.$metadata);
    }
    res.status(500).json({ error: 'Failed to fetch latest incident data from S3 (agentTwoOutput/)' });
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
