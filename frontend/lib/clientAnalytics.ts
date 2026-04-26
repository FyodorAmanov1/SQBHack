export type ClientTransaction = {
  at: string;
  amount: number;
  kind: string;
  description: string;
};

export type ClientAccount = {
  id: string;
  type: string;
  balance: number;
  limit: number;
  /** Hisob valyutasi, bo'lmaganda umumiy `currency` ishlatiladi */
  currency?: string;
};

export type ClientCreditProduct = {
  id: string;
  type: string;
  /** Chizma/karta: mavjud; qarz krediti uchun 0 */
  balance: number;
  limit: number;
  /** Qolgan asosiy qarz (kredit) */
  outstanding?: number;
};

export type ClientAnalytics = {
  client_id: string;
  name: string;
  creditScore: number;
  currency: string;
  balance: number;
  accounts: ClientAccount[];
  /** Faol kredit / plastik / muddatli mahsulotlar (sintetik) */
  credit_products?: ClientCreditProduct[];
  transactions: ClientTransaction[];
  history: { date: string; event: string }[];
  relatives?: { name: string; relation: string; linked_accounts: number }[];
};

export type AdvicePanel = { title: string; content: string };

export type OperatorAdviceResponse = {
  panels: AdvicePanel[];
  updatedAt: number;
};
