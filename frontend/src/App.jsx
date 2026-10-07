import React, { useState } from 'react';
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
