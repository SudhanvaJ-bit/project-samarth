import IEPHistory from '../components/IEPHistory'

export default function HistoryPage() {
  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">My IEPs</h1>
        <p className="text-slate-400 text-sm mt-1">Previously generated IEPs (stored locally).</p>
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <IEPHistory />
      </div>
    </div>
  )
}