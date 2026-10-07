import React, { useState } from 'react';
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
