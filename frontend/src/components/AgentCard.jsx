import React from 'react';
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
