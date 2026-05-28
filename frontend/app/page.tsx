"use client";

import { useState, useEffect } from "react";
import { Play, Trash2, Database, MessageSquare, PieChart, CheckCircle2, XCircle } from "lucide-react";

export default function Dashboard() {
  const [topic, setTopic] = useState("Investigating whether fine-tuning LLMs on logic rules causes catastrophic forgetting.");
  const [days, setDays] = useState(3);
  const [isRunning, setIsRunning] = useState(false);
  
  // Data States
  const [transcripts, setTranscripts] = useState([]);
  const [findings, setFindings] = useState([]);
  const [hypotheses, setHypotheses] = useState([]);
  
  // Tab State
  const [activeTab, setActiveTab] = useState("findings"); // "findings" | "audit"

  // Poll the backend every 3 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchTranscripts();
      fetchFindings();
      fetchHypotheses();
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchTranscripts = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/transcripts");
      setTranscripts(await res.json());
    } catch (e) {}
  };

  const fetchFindings = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/findings");
      setFindings(await res.json());
    } catch (e) {}
  };

  const fetchHypotheses = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/hypotheses");
      setHypotheses(await res.json());
    } catch (e) {}
  };

  const startSimulation = async () => {
    setIsRunning(true);
    await fetch("http://localhost:8000/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, days }),
    });
    setTimeout(() => setIsRunning(false), 3000); 
  };

  const clearDatabase = async () => {
    await fetch("http://localhost:8000/api/clear", { method: "DELETE" });
    setTranscripts([]);
    setFindings([]);
    setHypotheses([]);
  };

  // Calculate Metrics for the Audit Tab
  const totalHypotheses = hypotheses.length;
  const survivedHypotheses = hypotheses.filter((h: any) => h.status === 'supported').length;
  const rejectedHypotheses = hypotheses.filter((h: any) => h.status === 'rejected').length;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 font-sans">
      
      {/* HEADER & CONTROLS */}
      <header className="mb-8 border-b border-gray-800 pb-6">
        <h1 className="text-3xl font-bold mb-4 flex items-center gap-2">
          <Database className="text-blue-500" /> Research Town
        </h1>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm text-gray-400 mb-1">Research Topic</label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white outline-none focus:border-blue-500"
            />
          </div>
          <div className="w-24">
            <label className="block text-sm text-gray-400 mb-1">Days</label>
            <input
              type="number"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white outline-none focus:border-blue-500"
            />
          </div>
          <button
            onClick={startSimulation}
            disabled={isRunning}
            className="bg-blue-600 hover:bg-blue-500 px-6 py-2 rounded font-semibold flex items-center gap-2 transition-colors"
          >
            <Play size={18} /> {isRunning ? "Starting..." : "Run"}
          </button>
          <button
            onClick={clearDatabase}
            className="bg-red-900/50 hover:bg-red-800/80 text-red-200 px-4 py-2 rounded flex items-center gap-2 transition-colors"
          >
            <Trash2 size={18} /> Clear DB
          </button>
        </div>
      </header>

      {/* SPLIT SCREEN VIEW */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-[75vh]">
        
        {/* LEFT: Live Transcript (Always visible) */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg flex flex-col overflow-hidden">
          <div className="bg-gray-800/50 p-4 border-b border-gray-700 font-semibold flex items-center gap-2">
            <MessageSquare size={18} /> Live Debate
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {transcripts.length === 0 ? (
              <p className="text-gray-500 text-center mt-10">No debate logs yet. Start the simulation.</p>
            ) : (
              transcripts.map((msg: any, idx: number) => (
                <div key={idx} className="bg-gray-800 p-3 rounded shadow-sm border border-gray-700/50">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-bold text-blue-400">{msg.agent}</span>
                    <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">
                      Day {msg.day} • {msg.phase.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 whitespace-pre-wrap">{msg.content}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* RIGHT: Tabbed Interface */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg flex flex-col overflow-hidden">
          
          {/* Custom Tab Navigation */}
          <div className="flex border-b border-gray-800 bg-gray-800/20">
            <button 
              onClick={() => setActiveTab("findings")}
              className={`flex-1 p-4 font-semibold flex items-center justify-center gap-2 border-b-2 transition-colors ${activeTab === "findings" ? "border-blue-500 text-blue-400 bg-gray-800/50" : "border-transparent text-gray-400 hover:bg-gray-800/30"}`}
            >
              <Database size={18} /> Validated Findings
            </button>
            <button 
              onClick={() => setActiveTab("audit")}
              className={`flex-1 p-4 font-semibold flex items-center justify-center gap-2 border-b-2 transition-colors ${activeTab === "audit" ? "border-purple-500 text-purple-400 bg-gray-800/50" : "border-transparent text-gray-400 hover:bg-gray-800/30"}`}
            >
              <PieChart size={18} /> Hypothesis Audit
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            
            {/* TAB CONTENT: Findings */}
            {activeTab === "findings" && (
              <div className="space-y-4">
                {findings.length === 0 ? (
                  <p className="text-gray-500 text-center mt-10">Archivist has not validated any findings yet.</p>
                ) : (
                  findings.map((f: any, idx: number) => (
                    <div key={idx} className="bg-green-900/10 border border-green-800/30 p-4 rounded shadow-sm">
                      <div className="flex justify-between items-start mb-2">
                        <h3 className="font-bold text-green-400 text-lg">{f.title}</h3>
                        <span className="bg-green-900/50 text-green-300 text-xs px-2 py-1 rounded font-mono border border-green-800/50">
                          Conf: {f.confidence}/10
                        </span>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">{f.content}</p>
                      <p className="text-xs text-gray-500 text-right">— {f.author} (Day {f.day})</p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* TAB CONTENT: Hypothesis Audit */}
            {activeTab === "audit" && (
              <div className="space-y-6">
                
                {/* Metrics Cards */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-gray-800 border border-gray-700 p-4 rounded flex flex-col items-center justify-center">
                    <span className="text-gray-400 text-xs uppercase tracking-wider mb-1">Total Proposed</span>
                    <span className="text-2xl font-bold text-white">{totalHypotheses}</span>
                  </div>
                  <div className="bg-green-900/20 border border-green-800/30 p-4 rounded flex flex-col items-center justify-center">
                    <span className="text-green-500/80 text-xs uppercase tracking-wider mb-1 flex items-center gap-1"><CheckCircle2 size={12}/> Survived</span>
                    <span className="text-2xl font-bold text-green-400">{survivedHypotheses}</span>
                  </div>
                  <div className="bg-red-900/20 border border-red-800/30 p-4 rounded flex flex-col items-center justify-center">
                    <span className="text-red-500/80 text-xs uppercase tracking-wider mb-1 flex items-center gap-1"><XCircle size={12}/> Rejected</span>
                    <span className="text-2xl font-bold text-red-400">{rejectedHypotheses}</span>
                  </div>
                </div>

                {/* Hypotheses List */}
                <div className="space-y-3">
                  {hypotheses.length === 0 ? (
                    <p className="text-gray-500 text-center mt-6">No hypotheses proposed yet.</p>
                  ) : (
                    hypotheses.map((h: any, idx: number) => (
                      <div key={idx} className="bg-gray-800/50 border border-gray-700 p-4 rounded">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300 font-mono">Day {h.day}</span>
                          
                          {/* Status Badge */}
                          <span className={`text-xs px-2 py-1 rounded uppercase tracking-wide font-bold
                            ${h.status === 'supported' ? 'bg-green-900/50 text-green-400 border border-green-800/50' : 
                              h.status === 'rejected' ? 'bg-red-900/50 text-red-400 border border-red-800/50' : 
                              'bg-yellow-900/30 text-yellow-500 border border-yellow-800/50'}`}>
                            {h.status}
                          </span>
                        </div>
                        <p className="text-sm text-gray-300 mb-3 line-clamp-3 italic">"{h.content}"</p>
                        <div className="flex gap-4 text-xs">
                          <span className="text-gray-400">Votes For: <strong className="text-white">{h.votes_for}</strong></span>
                          <span className="text-gray-400">Votes Against: <strong className="text-white">{h.votes_against}</strong></span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}