import Link from "next/link";

export default function VositalarLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="h-[100dvh] overflow-y-auto bg-[#f4f4f5] text-zinc-900 dark:bg-[#0d0d0d] dark:text-zinc-100">
      <header className="flex shrink-0 items-center gap-3 border-b border-zinc-200/80 bg-white/90 px-4 py-3 backdrop-blur-md dark:border-zinc-800/80 dark:bg-zinc-950/90">
        <Link
          href="/"
          className="text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          ← Bosh sahifa
        </Link>
        <span className="text-zinc-300 dark:text-zinc-600">|</span>
        <Link
          href="/vositalar"
          className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100"
        >
          Vositalar
        </Link>
      </header>
      {children}
    </div>
  );
}
