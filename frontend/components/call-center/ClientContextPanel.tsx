"use client";

import type { ClientAnalytics, ClientAccount, ClientCreditProduct } from "@/lib/clientAnalytics";

type Props = {
  data: ClientAnalytics | null;
  loading: boolean;
  error: string | null;
};

function formatMoney(
  n: number,
  currency: string,
): string {
  try {
    return new Intl.NumberFormat("uz-UZ", {
      style: "currency",
      currency: currency === "UZS" ? "UZS" : currency,
      maximumFractionDigits: currency === "UZS" ? 0 : 2,
    }).format(n);
  } catch {
    return `${n.toLocaleString("uz-UZ")} ${currency}`;
  }
}

function accountCurrency(acc: ClientAccount, defaultCur: string): string {
  return (acc.currency || defaultCur).toUpperCase();
}

function CreditProductRow({ p, defaultCur }: { p: ClientCreditProduct; defaultCur: string }) {
  const hasOutstanding =
    p.outstanding != null && p.outstanding > 0;
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{p.type}</p>
      {hasOutstanding && (
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Qarz:{" "}
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            {formatMoney(p.outstanding as number, defaultCur)}
          </span>
        </p>
      )}
      {p.limit > 0 && (
        <p className="mt-0.5 text-xs text-zinc-500">
          Limit: {formatMoney(p.limit, defaultCur)}
        </p>
      )}
      {p.balance > 0 && !hasOutstanding && (
        <p className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {formatMoney(p.balance, defaultCur)}
        </p>
      )}
      {p.balance > 0 && hasOutstanding && p.type.toLowerCase().includes("chizma") && (
        <p className="mt-0.5 text-xs text-zinc-500">
          Mavjud chizma: {formatMoney(p.balance, defaultCur)}
        </p>
      )}
    </div>
  );
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

  const products = data.credit_products ?? [];

  return (
    <div className="space-y-5">
      <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">1. Mijoz</h2>

      <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Mijoz ID</p>
        <p className="mt-1 font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {data.client_id}
        </p>
        <p className="mt-3 text-xl font-semibold">{data.name}</p>
        <div className="mt-4 flex flex-wrap gap-4">
          <div>
            <p className="text-xs text-zinc-500">Kredit reytingi</p>
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
        <h3 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Hisoblar</h3>
        <div className="grid gap-2">
          {data.accounts.map((acc) => {
            const cur = accountCurrency(acc, data.currency);
            return (
              <div
                key={acc.id}
                className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {acc.type}
                </p>
                <p className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {formatMoney(acc.balance, cur)}
                </p>
                {acc.limit > 0 && (
                  <p className="text-xs text-zinc-500">
                    Limit: {formatMoney(acc.limit, cur)}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {products.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
            Faol mahsulotlar
          </h3>
          <div className="grid gap-2">
            {products.map((p) => (
              <CreditProductRow key={p.id} p={p} defaultCur={data.currency} />
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Tranzaksiyalar</h3>
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
