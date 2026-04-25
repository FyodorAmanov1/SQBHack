import { TtsTool } from "@/components/tools/TtsTool";

export default function MatndanOvozPage() {
  return (
    <div>
      <div className="border-b border-zinc-200 bg-white/80 px-4 py-4 dark:border-zinc-800 dark:bg-zinc-900/60">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Matndan ovoz
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Matnni yuboring, OmniVoice orqali WAV qaytadi va brauzerda ijro
          etiladi.
        </p>
      </div>
      <TtsTool />
    </div>
  );
}
