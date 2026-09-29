import HistoryClient from './components/HistoryClient';

export default function HistoryPage() {
  return (
    <div className="flex-1 max-w-6xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 md:pb-6 animate-in fade-in duration-500">
      <HistoryClient />
    </div>
  );
}
