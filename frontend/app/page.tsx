import { VoiceChat } from "@/components/VoiceChat";
import { useState } from "react";

const MOCK_CLIENT = {
  name: "Sarah Johnson",
  creditScore: 742,
  accounts: [
    { id: "1", type: "Credit Card", balance: 1250, limit: 5000 },
    { id: "2", type: "Personal Loan", balance: 4500, limit: 10000 },
  ],
  history: [
    { date: "2024-03-01", event: "On-time payment - Credit Card" },
    { date: "2024-02-15", event: "New account opened - Personal Loan" },
  ]
};

export default function Home() {
  return (
    <main className="h-[100dvh] flex overflow-hidden bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
      {/* Left Panel: Analytics & Client Data */}
      <section className="w-1/2 lg:w-2/3 border-r border-zinc-200 dark:border-zinc-800 p-6 overflow-y-auto">
        <h1 className="text-2xl font-bold mb-6">Client Dashboard</h1>
        
        <div className="bg-white dark:bg-zinc-900 rounded-xl p-6 shadow-sm border border-zinc-100 dark:border-zinc-800 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">{MOCK_CLIENT.name}</h2>
            <div className="text-right">
              <span className="text-sm text-zinc-500 block">Credit Score</span>
              <span className="text-2xl font-bold text-emerald-600">{MOCK_CLIENT.creditScore}</span>
            </div>
          </div>
        </div>

        <h3 className="text-lg font-semibold mb-4">Active Accounts</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {MOCK_CLIENT.accounts.map(acc => (
            <div key={acc.id} className="bg-white dark:bg-zinc-900 p-4 rounded-lg border border-zinc-100 dark:border-zinc-800 shadow-sm">
              <h4 className="font-medium text-zinc-700 dark:text-zinc-300">{acc.type}</h4>
              <p className="text-2xl font-semibold mt-2">${acc.balance}</p>
              <p className="text-sm text-zinc-500">Limit: ${acc.limit}</p>
            </div>
          ))}
        </div>

        <h3 className="text-lg font-semibold mb-4">History & Analytics</h3>
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-100 dark:border-zinc-800 shadow-sm divide-y divide-zinc-100 dark:divide-zinc-800">
          {MOCK_CLIENT.history.map((item, i) => (
            <div key={i} className="p-4 flex gap-4">
              <span className="text-sm text-zinc-400 whitespace-nowrap">{item.date}</span>
              <span className="text-sm">{item.event}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Right Panel: Voice / AI Chat */}
      <section className="w-1/2 lg:w-1/3 flex flex-col h-full bg-white dark:bg-zinc-900">
        <div className="p-4 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950">
          <h2 className="text-lg font-semibold">AI Assistant</h2>
          <p className="text-xs text-zinc-500">Analyze conversations and get recommendations</p>
        </div>
        <div className="flex-1 relative">
          <VoiceChat />
        </div>
      </section>
    </main>
  );
}
