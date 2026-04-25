import Link from "next/link";

const tools = [
  {
    href: "/",
    title: "Ovozli suhbat",
    desc: "Mikrofon orqali real vaqt rejimida STT, LLM va TTS (WebSocket).",
    tag: "Asosiy",
  },
  {
    href: "/vositalar/matn",
    title: "Matn suhbati",
    desc: "Faqat matn: serverdagi LLM ga REST orqali yuboriladi.",
    tag: "REST",
  },
  {
    href: "/vositalar/stt",
    title: "Nutqdan matn",
    desc: "Audio faylni yuklang, transkripsiya oling (POST /stt).",
    tag: "REST",
  },
  {
    href: "/vositalar/tts",
    title: "Matndan ovoz",
    desc: "Matn yozing, WAV ovozini tinglang (POST /tts).",
    tag: "REST",
  },
] as const;

export default function VositalarHubPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        O‘zbek tilidagi vositalar
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        STT, TTS, matnli va ovozli suhbat — barchasi bir backend bilan. Ovozli
        rejim WebSocket, qolganlari HTTP orqali ishlaydi.
      </p>
      <ul className="mt-8 grid gap-4 sm:grid-cols-2">
        {tools.map((t) => (
          <li key={t.href + t.title}>
            <Link
              href={t.href}
              className="flex h-full flex-col rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-emerald-300/80 hover:shadow-md dark:border-zinc-700 dark:bg-zinc-900/80 dark:hover:border-emerald-700/50"
            >
              <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                {t.tag}
              </span>
              <span className="mt-2 text-base font-semibold text-zinc-900 dark:text-zinc-50">
                {t.title}
              </span>
              <span className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                {t.desc}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
