import os

components = {
    'ProblemInput.jsx': '''import React, { useState } from 'react';
export default function ProblemInput({ onSubmit, isLoading }) {
  const [problem, setProblem] = useState('');
  return (
    <div className="p-4 border rounded shadow bg-white dark:bg-gray-800">
      <h2 className="text-xl font-semibold mb-2">What problem do you want to solve?</h2>
      <textarea 
        className="w-full p-2 border rounded mb-2 dark:bg-gray-700" 
        rows="4" 
        value={problem} 
        onChange={(e) => setProblem(e.target.value)}
        placeholder="Describe your complex problem here..."
      />
      <button 
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        onClick={() => onSubmit(problem)}
        disabled={isLoading || !problem.trim()}
      >
        {isLoading ? 'Processing...' : 'Solve with CHAI'}
      </button>
    </div>
  );
}
''',
    'AgentCard.jsx': '''import React from 'react';
export default function AgentCard({ agentName, status, output }) {
  const isComplete = status === 'success';
  return (
    <div className={`p-4 border rounded shadow ${isComplete ? 'border-green-500' : 'border-gray-300'} bg-white dark:bg-gray-800`}>
      <h3 className="font-bold text-lg capitalize">{agentName}</h3>
      <p className="text-sm text-gray-500 mb-2">Status: {status}</p>
      {isComplete && output && (
        <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-auto max-h-40">
          {JSON.stringify(output, null, 2)}
        </pre>
      )}
    </div>
  );
}
''',
    'FinalSolution.jsx': '''import React from 'react';
export default function FinalSolution({ result }) {
  if (!result) return null;
  return (
    <div className="p-4 border-2 border-blue-500 rounded shadow bg-blue-50 dark:bg-gray-800 dark:border-blue-700 mt-6">
      <h2 className="text-2xl font-bold mb-4 text-blue-800 dark:text-blue-300">Final Synthesized Solution</h2>
      <div className="whitespace-pre-wrap">{result.final_synthesized_answer}</div>
      {result.limitations && result.limitations.length > 0 && (
        <div className="mt-4 pt-4 border-t border-blue-200">
          <h4 className="font-semibold text-red-600">Limitations & Warnings:</h4>
          <ul className="list-disc pl-5 text-sm text-gray-700 dark:text-gray-300">
            {result.limitations.map((limit, i) => <li key={i}>{limit}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
'''
}

app_jsx = '''import React, { useState } from 'react';
import ProblemInput from './components/ProblemInput';
import AgentCard from './components/AgentCard';
import FinalSolution from './components/FinalSolution';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSolve = async (problem) => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch('http://localhost:8000/api/solve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem })
      });
      if (!response.ok) throw new Error('API request failed');
      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-gray-100 p-8">
      <div className="max-w-5xl mx-auto">
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">CHAI</h1>
          <p className="text-xl mt-2 text-gray-600 dark:text-gray-400">Coordinated Hybrid Agentic Intelligence</p>
          <p className="text-sm text-gray-500">One Intelligence → Many Minds → One Unified Outcome.</p>
        </header>

        <ProblemInput onSubmit={handleSolve} isLoading={isLoading} />
        
        {error && <div className="p-4 mt-4 bg-red-100 text-red-700 rounded shadow">{error}</div>}

        {result && (
          <div className="mt-8">
            <h2 className="text-2xl font-bold mb-4">Agent Execution</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {result.agent_execution_statuses.map(status => (
                <AgentCard 
                  key={status.agent_name}
                  agentName={status.agent_name}
                  status={status.status}
                  output={result.agent_outputs[status.agent_name]}
                />
              ))}
            </div>
            
            <FinalSolution result={result} />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
'''

import_css = '''@tailwind base;
@tailwind components;
@tailwind utilities;
'''

tailwind_config = '''/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
'''

base_dir = 'frontend/src/components'
os.makedirs(base_dir, exist_ok=True)

for name, content in components.items():
    with open(os.path.join(base_dir, name), 'w') as f:
        f.write(content)

with open('frontend/src/App.jsx', 'w') as f:
    f.write(app_jsx)
    
with open('frontend/src/index.css', 'w') as f:
    f.write(import_css)
    
with open('frontend/tailwind.config.js', 'w') as f:
    f.write(tailwind_config)
    
print("Frontend components scaffolded successfully.")
