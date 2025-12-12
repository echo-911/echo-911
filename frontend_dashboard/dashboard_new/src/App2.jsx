import React, { useState, useEffect } from 'react';
import { GoogleMap, LoadScript, Marker } from '@react-google-maps/api';
import backgroundImage from './hackathon2.jpg';

// Mock data for agents
const MOCK_KEY_DETAILS = {
  sentiment: 'Neutral',
  threatLevel: 'Critical',
  eventDetails: 'Fire Emergency - Residential house fire with possible occupants trapped inside.',
};
const MOCK_DISPATCHER_INFO = {
  dispatcherName1: 'Sarah Johnson',
  dispatcherName2: 'John Nolan',
  dispatcherName3: 'Peruna Smith',
}; 
const MOCK_CHECKLIST_INFO = [
  { task: 'Fire engine dispatched', status: 'Complete', time: '1 min' },
  { task: 'Scene secured and perimeter established', status: 'In Progress', time: '3 min' },
  { task: 'Occupants evacuated', status: 'Pending', time: '-- min' },
  { task: 'Fire suppression started', status: 'Pending', time: '-- min' },
  { task: 'Medical assessment of casualties', status: 'Pending', time: '-- min' },
];



const MOCK_ADDITIONAL_INFO = [
  { detail: 'Patient has history of cardiac issues.', time: '0 min' },
  { detail: 'Nearest hospital (St. Mary\'s) is 3 blocks away.', time: '4 min' },
  { detail: 'Weather: Clear, no traffic incidents reported.', time: '0 min' },
];

const EmergencyDashboard = () => {
  const [transcript, setTranscript] = useState([]);
  const [location, setLocation] = useState(null);
  const [currentAddress, setCurrentAddress] = useState('6425 Boaz Lane, Dallas, TX 75205');
  const [mapError, setMapError] = useState(null);
  const [isLoadingLocation, setIsLoadingLocation] = useState(true);

  const GOOGLE_MAPS_API_KEY = process.env.REACT_APP_GOOGLE_MAPS_API_KEY || "KEY_HERE";

  const [jsonData, setJsonData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchLatestJsonFromApi = async () => {
      try {
        setLoading(true);
        const response = await fetch('http://localhost:4000/api/latest-json');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setJsonData(data);
        setError(null);
      } catch (err) {
        setError('Error fetching data from API: ' + err.message);
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchLatestJsonFromApi();
  }, []);

  // Function to geocode an address
  const geocodeAddress = (address) => {
    setIsLoadingLocation(true);
    setMapError(null);
    
    console.log('Geocoding address:', address);
    
    fetch(`https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(address)}&key=${GOOGLE_MAPS_API_KEY}`)
      .then(response => response.json())
      .then(data => {
        console.log('Geocoding response:', data);
        
        if (data.status === 'OK' && data.results && data.results.length > 0) {
          const { lat, lng } = data.results[0].geometry.location;
          setLocation({ lat, lng });
          setCurrentAddress(data.results[0].formatted_address);
          console.log('Location set:', { lat, lng });
          console.log('Formatted address:', data.results[0].formatted_address);
        } else if (data.status === 'ZERO_RESULTS') {
          console.error("No results found for address:", address);
          setMapError('Address not found');
        } else if (data.status === 'REQUEST_DENIED') {
          console.error("Geocoding request denied:", data.error_message);
          setMapError(`API Error: ${data.error_message || 'Request denied'}`);
        } else {
          console.error("Geocoding failed:", data.status, data.error_message);
          setMapError(`Geocoding failed: ${data.status}`);
        }
        setIsLoadingLocation(false);
      })
      .catch(error => {
        console.error("Error fetching geocode data:", error);
        setMapError(`Network error: ${error.message}`);
        setIsLoadingLocation(false);
      });
  };

  // Load default address on component mount
  useEffect(() => {
    const defaultAddress = '6425 Boaz Lane, Dallas, TX 75205';
    geocodeAddress(defaultAddress);
  }, []);

  // Function to handle file input and parse transcript
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        const lines = text.split('\n').filter(line => line.trim() !== '');
        const parsedTranscript = lines.map(line => {
          const match = line.match(/^\[(.*?)\]: "(.*)"(?: \((.*?)\))?$/);
          if (match) {
            const [_, speaker, message, time] = match;
            return { speaker, message, time };
          }
          return null;
        }).filter(Boolean);
        setTranscript(parsedTranscript);

        // Parse location from the transcript
        const locationLine = parsedTranscript.find(line => 
          line.message.toLowerCase().includes('address') || 
          line.message.toLowerCase().includes('street') ||
          line.message.toLowerCase().includes('location')
        );
        
        if (locationLine) {
          // Try to extract address from the message
          const message = locationLine.message;
          let extractedAddress = null;
          
          // Look for patterns like "Address: 123 Main St" or "I'm at 123 Main St"
          const addressPatterns = [
            /(?:address|location):\s*(.+)/i,
            /(?:i'm at|located at|at)\s+(.+)/i,
            /(\d+\s+[^,]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|way|blvd|boulevard)[^,]*)/i
          ];
          
          for (const pattern of addressPatterns) {
            const match = message.match(pattern);
            if (match) {
              extractedAddress = match[1].trim();
              break;
            }
          }
          
          if (extractedAddress) {
            console.log('Extracted address from transcript:', extractedAddress);
            geocodeAddress(extractedAddress);
          }
        }
      };
      reader.readAsText(file);
    }
  };

  const mapContainerStyle = {
    width: '100%',
    height: '100%',
    borderRadius: '1.5rem',
  };

  const center = location || { lat: 40.7829, lng: -73.9654 }; // Default to NYC

  const mapOptions = {
    disableDefaultUI: true,
    zoomControl: true,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,
  };

  const handleMapLoad = () => {
    console.log('Google Maps loaded successfully');
  };

  const handleMapError = (error) => {
    console.error('Google Maps load error:', error);
    setMapError('Failed to load Google Maps');
  };

  return (
    <div
      className="min-h-screen p-6 flex items-center justify-center"
      style={{
        backgroundImage: `url(${backgroundImage})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-16 left-20 w-80 h-80 bg-blue-400/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-20 right-16 w-96 h-96 bg-purple-400/8 rounded-full blur-3xl"></div>
        <div className="absolute top-1/3 right-1/3 w-64 h-64 bg-cyan-300/6 rounded-full blur-3xl"></div>
        <div className="absolute bottom-1/3 left-1/4 w-72 h-72 bg-indigo-300/8 rounded-full blur-3xl"></div>
      </div>

      <div className="relative z-10 w-full max-w-7xl space-y-6">
        <div className="backdrop-blur-xl bg-white/8 border border-white/15 rounded-3xl p-3">
          <div className="text-center">
            <span className="text-xl font-sans font-bold text-white">
              Hello Aaryaa, these are the additional details.
            </span>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-7 space-y-4">
            {/* Top Left - Transcript with file input */}
            <div className="backdrop-blur-xl bg-white/6 border border-white/15 rounded-3xl p-8 h-[200px] hover:scale-[1.01] hover:bg-white/8 transition-all duration-500">
            <div className="flex flex-col mb-6">
  <div className="flex items-center justify-between mb-2">
    <h3 className="text-2xl font-extralight text-white/95 tracking-wide">
      Summary
    </h3>
    <span className="text-xs font-medium text-white/70 bg-white/10 px-3 py-2 rounded-full backdrop-blur-sm">
      Post-Processing
    </span>
  </div>

  {/* Summary paragraph */}
  <p className="text-white/70 text-sm leading-relaxed">
    A residential house fire has been reported at 6425 Boaz Lane, Dallas, TX. Flames are visible from the second-floor windows, and screaming indicates possible occupants trapped inside. The situation is critical. The nearest fire station is 2 miles away (~5 min response), and paramedics have been dispatched alongside the fire department. Weather conditions are clear with calm wind, minimizing fire spread risk. The caller is in a safe location across the street.
  </p>
</div>

              
              <div className="text-white/85 text-sm font-light leading-relaxed space-y-4 h-[250px] overflow-y-auto">
                {transcript.length > 0 ? (
                  transcript.map((item, index) => (
                    <div
                      key={index}
                      className={`backdrop-blur-sm bg-white/4 rounded-2xl p-4 border-l-4 ${item.speaker === 'Dispatcher' ? 'border-blue-300/60' : 'border-green-300/60'}`}
                    >
                      <p className="font-medium text-white/95">[{item.speaker}]: "{item.message}"</p>
                      <span className="text-xs text-white/60 font-light">{item.time || 'Timestamp N/A'}</span>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center space-x-2 px-4 py-2">
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Middle - Key Details */}
            <div className="border border-white/15 rounded-3xl p-6 h-[auto] hover:scale-[1.01] transition-all duration-300">
  <h4 className="text-xl font-extralight text-white/95 tracking-wide mb-4">Key Information</h4>
  
  <div className="grid grid-cols-3 gap-3 text-center mb-4">
    <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
      <div className="text-xl font-thin text-indigo-300">{MOCK_KEY_DETAILS.sentiment}</div>
      <div className="text-xs font-light text-white/70 mt-1">Sentiment</div>
    </div>
    <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
      <div className="text-xl font-thin text-red-300">{MOCK_KEY_DETAILS.threatLevel}</div>
      <div className="text-xs font-light text-white/70 mt-1">Threat Level</div>
    </div>
    <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
      <div className="text-sm font-thin text-cyan-300 text-center px-2">{MOCK_KEY_DETAILS.eventDetails}</div>
      <div className="text-xs font-light text-white/70 mt-1"></div>
    </div>
  </div>

  {/* Paragraph summarizing key area information */}
  <p className="text-white/70 text-sm leading-relaxed">
    {`The caller reports visible flames from the second-floor windows and possible occupants trapped inside. The nearest fire station is approximately 2 miles away (~5 min response), and paramedics have been dispatched alongside the fire department. Weather conditions are clear with calm wind, minimizing fire spread risk.`}
  </p>
</div>


            <div className="backdrop-blur-xl bg-white/6 border border-white/15 rounded-3xl p-6 h-[205px] hover:scale-[1.01] transition-all duration-300">
              <h4 className="text-xl font-extralight text-white/95 tracking-wide mb-4">Dispatchers</h4>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
                  <div className="text-xl font-thin text-indigo-300">{MOCK_DISPATCHER_INFO.dispatcherName1}</div>
                  <div className="text-xs font-light text-white/70 mt-1">Firefighter</div>
                </div>
                <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
                  <div className="text-xl font-thin text-red-300">{MOCK_DISPATCHER_INFO.dispatcherName2}</div>
                  <div className="text-xs font-light text-white/70 mt-1">Firefighter</div>
                </div>
                <div className="bg-white/5 rounded-2xl w-[180px] h-[110px] flex flex-col items-center justify-center mx-auto backdrop-blur-sm">
                  <div className="text-sm font-thin text-cyan-300 text-center px-2">{MOCK_DISPATCHER_INFO.dispatcherName3}</div>
                  <div className="text-xs font-light text-white/70 mt-1">EMT</div>
                </div>
              </div>
            </div>
          </div>

          

          <div className="col-span-5 space-y-6">
            {/* Top Right - Map */}
            <div className="backdrop-blur-xl bg-white/6 border border-white/15 rounded-3xl p-3 h-100px] hover:scale-[1.02] transition-all duration-300">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-lg font-light text-white/95 tracking-wide">Caller's Location</h4>
                <div className="w-3 h-3 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/30"></div>
              </div>
              <div className="h-[125px] relative">
                {mapError ? (
                  <div className="w-full h-full bg-red-900/20 rounded-3xl flex items-center justify-center border border-red-400/20">
                    <div className="text-center">
                      <div className="text-red-300 text-sm font-medium mb-2">Map Error</div>
                      <div className="text-red-200/80 text-xs px-4">{mapError}</div>
                    </div>
                  </div>
                ) : isLoadingLocation ? (
                  <div className="w-full h-full bg-blue-900/20 rounded-3xl flex items-center justify-center">
                    <div className="text-center">
                      <div className="animate-spin w-8 h-8 border-2 border-blue-300 border-t-transparent rounded-full mx-auto mb-2"></div>
                      <div className="text-blue-300 text-sm">Loading location...</div>
                    </div>
                  </div>
                ) : (
                  <LoadScript 
                    googleMapsApiKey={GOOGLE_MAPS_API_KEY}
                    onLoad={handleMapLoad}
                    onError={handleMapError}
                  >
                    <GoogleMap
                      mapContainerStyle={mapContainerStyle}
                      center={center}
                      zoom={15}
                      options={mapOptions}
                    >
                      {location && (
                        <Marker 
                          position={location}
                          title={currentAddress}
                        />
                      )}
                    </GoogleMap>
                  </LoadScript>
                )}
              </div>
            </div>

            {/* Bottom Right - Additional Information */}
            <div className="backdrop-blur-xl bg-white/6 border border-white/15 rounded-3xl p-6 h-[500px] hover:scale-[1.02] transition-all duration-300">
              <h4 className="text-lg font-light text-white/95 tracking-wide mb-4">CheckList</h4>
              <div className="space-y-3">
    {MOCK_CHECKLIST_INFO.map((item, index) => (
        <div key={index} className="flex justify-between items-center bg-white/5 rounded-xl p-4 backdrop-blur-sm hover:bg-white/10 transition-colors">
            <span className="text-white/85 font-light text-sm">{item.task}</span>
            <span className="text-cyan-300 font-bold text-sm">{item.status} - {item.time}</span>
        </div>
    ))}
</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmergencyDashboard;