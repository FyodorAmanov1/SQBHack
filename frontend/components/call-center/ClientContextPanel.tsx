"use client";

import type { ClientAnalytics } from "@/lib/clientAnalytics";

type Props = {
  data: ClientAnalytics | null;
  loading: boolean;
  error: string | null;
};

function formatMoney(n: number, currency: string): string {
  try {
    return new Intl.NumberFormat("uz-UZ", {
      style: "currency",
      currency: currency === "UZS" ? "UZS" : "USD",
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `${n.toLocaleString("uz-UZ")} ${currency}`;
  }
}

export function ClientContextPanel({ data, loading, error }: Props) {
  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm text-zinc-500">Mijoz ma’lumoti yuklanmoqda…</p>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
        {error || "Ma’lumot yo‘q"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Mijoz ID
        </p>
        <p className="mt-1 font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {data.client_id}
        </p>
        <p className="mt-4 text-xl font-semibold">{data.name}</p>
        <div className="mt-4 flex flex-wrap gap-4">
          <div>
            <p className="text-xs text-zinc-500">Reyting</p>
            <p className="text-2xl font-bold text-emerald-600">{data.creditScore}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">Jami qoldiq</p>
            <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
              {formatMoney(data.balance, data.currency)}
            </p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
          Hisoblar
        </h3>
        <div className="grid gap-3">
          {data.accounts.map((acc) => (
            <div
              key={acc.id}
              className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <p className="font-medium text-zinc-800 dark:text-zinc-200">{acc.type}</p>
              <p className="mt-1 text-lg font-semibold">
                {formatMoney(acc.balance, data.currency)}
              </p>
              <p className="text-xs text-zinc-500">
                Limit: {formatMoney(acc.limit, data.currency)}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
          Tranzaksiyalar
        </h3>
        <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs uppercase text-zinc-500 dark:bg-zinc-950">
              <tr>
                <th className="px-3 py-2">Vaqt</th>
                <th className="px-3 py-2">Summa</th>
                <th className="px-3 py-2">Tavsif</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {data.transactions.map((t, i) => (
                <tr key={`${t.at}-${i}`} className="bg-white dark:bg-zinc-900">
                  <td className="whitespace-nowrap px-3 py-2 text-zinc-600">
                    {t.at.replace("T", " ").slice(0, 16)}
                  </td>
                  <td
                    className={
                      t.amount < 0
                        ? "px-3 py-2 text-rose-600"
                        : "px-3 py-2 text-emerald-600"
                    }
                  >
                    {formatMoney(t.amount, data.currency)}
                  </td>
                  <td className="px-3 py-2 text-zinc-800 dark:text-zinc-200">
                    {t.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
