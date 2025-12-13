import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import EmergencyDashboard from "./EmergencyDashboardInitial"; 
import App2 from "./App2"; 

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<EmergencyDashboard />} />
        <Route path="/app2" element={<App2 />} />
      </Routes>
    </Router>
  );
}