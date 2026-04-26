export type ClientTransaction = {
  at: string;
  amount: number;
  kind: string;
  description: string;
};

export type ClientAnalytics = {
  client_id: string;
  name: string;
  creditScore: number;
  currency: string;
  balance: number;
  accounts: { id: string; type: string; balance: number; limit: number }[];
  transactions: ClientTransaction[];
  history: { date: string; event: string }[];
  relatives?: { name: string; relation: string; linked_accounts: number }[];
};

export type AdvicePanel = { title: string; content: string };

export type OperatorAdviceResponse = {
  panels: AdvicePanel[];
  updatedAt: number;
};
