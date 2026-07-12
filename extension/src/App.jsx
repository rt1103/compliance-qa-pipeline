import React, { useState, useEffect, useRef } from 'react';

export default function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [isAuditing, setIsAuditing] = useState(false);
  const [streamLogs, setStreamLogs] = useState([]);
  const [finalReport, setFinalReport] = useState(null);
  const logContainerRef = useRef(null);

  // 1. Listen for toolbar extension clicks to toggle the layout
  useEffect(() => {
    const handleMessage = (request) => {
      if (request.action === "toggleSidebar") {
        setIsOpen((prev) => !prev);
      }
    };
    chrome.runtime.onMessage.addListener(handleMessage);
    return () => chrome.runtime.onMessage.removeListener(handleMessage);
  }, []);

  // 2. NEW: Clean the dashboard state completely whenever the panel closes
  useEffect(() => {
    if (!isOpen) {
      setStreamLogs([]);
      setFinalReport(null);
      setIsAuditing(false);
    }
  }, [isOpen]);

  // 3. Keep the logs scrolled down automatically
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [streamLogs]);

  const startComplianceAudit = async () => {
    setIsAuditing(true);
    setStreamLogs([]);
    setFinalReport(null);

    try {
      const response = await fetch('http://127.0.0.1:8000/audit/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_url: window.location.href })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;

        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.replace('data: ', '').trim();
              if (dataStr === '[DONE]') break;

              if (dataStr) {
                const data = JSON.parse(dataStr);
                setStreamLogs((prev) => [...prev, { stage: data.stage, status: data.status }]);
                
                if (data.report) {
                  setFinalReport(data.report);
                }
              }
            }
          }
        }
      }
    } catch (err) {
      setStreamLogs((prev) => [...prev, { stage: "Connection Error", status: "Failed linking to local server. Ensure FastAPI is active." }]);
    } finally {
      setIsAuditing(false);
    }
  };

  return (
    <div 
      className="fixed top-0 w-[400px] h-screen bg-slate-900 text-slate-50 z-[999999] shadow-2xl flex flex-col font-sans transition-all duration-300 ease-in-out"
      style={{ right: isOpen ? '0px' : '-420px' }}
    >
      {/* Upper Brand Navigation Header */}
      <div className="flex justify-between items-center px-6 py-5 bg-slate-800 border-b border-slate-700">
        <h1 className="m-0 text-2xl font-bold text-sky-400">Brand Guardian AI</h1>
        <button 
          onClick={() => setIsOpen(false)}
          className="bg-transparent border-none text-slate-400 text-4xl cursor-pointer hover:text-red-500 transition-colors leading-none"
        >
          &times;
        </button>
      </div>

      {/* Main Container Body */}
      <div className="p-6 flex-grow overflow-y-auto space-y-6">
        
        {/* Large Centered Premium Bookmark Emblem */}
        <div className="flex justify-center items-center py-4">
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            fill="none" 
            viewBox="0 0 24 24" 
            strokeWidth={1.5} 
            stroke="currentColor" 
            className="w-28 h-28 text-sky-400 drop-shadow-[0_0_15px_rgba(56,189,248,0.4)]"
          >
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z" 
            />
          </svg>
        </div>

        {/* Audit Call-To-Action Trigger Button */}
        <button
          onClick={startComplianceAudit}
          disabled={isAuditing}
          className="w-full p-4 bg-sky-600 text-white rounded-lg text-lg font-extrabold transition-colors hover:bg-sky-700 disabled:bg-slate-700 disabled:text-slate-400 disabled:cursor-not-allowed shadow-lg"
        >
          {isAuditing ? 'Auditing in progress...' : 'Start Compliance Audit'}
        </button>

        {/* Live Logs Component Feed */}
        <div ref={logContainerRef} className="space-y-3 max-h-[35vh] overflow-y-auto pr-1">
          {streamLogs.map((log, idx) => (
            <div key={idx} className="bg-slate-800 p-4 rounded-lg border-l-4 border-sky-400 shadow-md">
              <div className="font-bold text-base text-slate-100 mb-1">{log.stage}</div>
              <div className="text-sm text-slate-300 leading-relaxed">{log.status}</div>
            </div>
          ))}
        </div>

        {/* Final Audit Output Presentation Card */}
        {finalReport && (
          <div className={`p-5 rounded-lg border shadow-xl transition-all ${
            finalReport.status === 'PASS' 
              ? 'border-emerald-600 bg-emerald-950/40 text-emerald-100' 
              : 'border-rose-600 bg-rose-950/40 text-rose-100'
          }`}>
            <h2 className={`mt-0 font-extrabold text-xl mb-2 ${finalReport.status === 'PASS' ? 'text-emerald-400' : 'text-rose-400'}`}>
              Result Status: {finalReport.status}
            </h2>
            <p className="leading-relaxed text-base mb-3 text-slate-200">{finalReport.final_report}</p>
            
            {finalReport.compliance_results?.length > 0 && (
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300 border-t border-slate-800 pt-3">
                {finalReport.compliance_results.map((item, i) => (
                  <li key={i} className="leading-relaxed">
                    <span className="font-bold text-rose-400">{item.severity}:</span> {item.description}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}