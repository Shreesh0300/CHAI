import React from 'react';
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
