import React from 'react';

export default function Loading() {
  return (
    <div className="flex-1 max-w-5xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 md:pb-6 animate-pulse">
      {/* Header skeleton */}
      <div className="bg-surface-container-low border border-outline-variant/50 rounded-xl p-5 shadow-sm flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-container-high" />
          <div className="space-y-2">
            <div className="h-5 w-40 bg-surface-container-high rounded" />
            <div className="h-3 w-64 bg-surface-container-high/60 rounded" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary-container animate-ping" />
          <span className="text-xs text-on-surface-variant font-mono">Cargando...</span>
        </div>
      </div>

      {/* Grid skeletons */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="bg-surface-container-low/70 border border-outline-variant/30 rounded-xl p-4 space-y-4 shadow-sm"
          >
            <div className="h-40 w-full bg-surface-container-high/60 rounded-lg" />
            <div className="h-4 w-3/4 bg-surface-container-high rounded" />
            <div className="h-3 w-1/2 bg-surface-container-high/60 rounded" />
            <div className="flex justify-between items-center pt-2">
              <div className="h-6 w-20 bg-surface-container-high rounded" />
              <div className="h-8 w-24 bg-surface-container-high rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
