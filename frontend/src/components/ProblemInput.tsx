import React, { useState } from 'react';

export interface ProblemInputProps {
  onSubmit: (problem: string) => void | Promise<void>;
  isLoading: boolean;
}

export default function ProblemInput({ onSubmit, isLoading }: ProblemInputProps) {
  const [problem, setProblem] = useState<string>('');

  const handleSubmit = () => {
    if (problem.trim() && !isLoading) {
      onSubmit(problem);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-4 border rounded shadow bg-white dark:bg-gray-800 dark:border-gray-700">
      <h2 className="text-xl font-semibold mb-2">What problem do you want to solve?</h2>
      <textarea 
        className="w-full p-2 border rounded mb-2 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600" 
        rows={4} 
        value={problem} 
        onChange={(e) => setProblem(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Describe your complex problem here... (Press Ctrl+Enter or click Solve)"
      />
      <button 
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
        onClick={handleSubmit}
        disabled={isLoading || !problem.trim()}
      >
        {isLoading ? 'Processing...' : 'Solve with CHAI'}
      </button>
    </div>
  );
}
