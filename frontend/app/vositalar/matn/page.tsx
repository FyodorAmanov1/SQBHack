import { TextChatTool } from "@/components/tools/TextChatTool";

export default function MatnSuhbatPage() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-zinc-200 bg-white/80 px-4 py-4 dark:border-zinc-800 dark:bg-zinc-900/60">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Matn suhbati
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          LLM bilan yozma muloqot (POST /llm). Enter — yuborish, Shift+Enter —
          yangi qator.
        </p>
      </div>
      <TextChatTool />
    </div>
  );
}
