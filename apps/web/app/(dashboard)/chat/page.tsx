import { ChatUI } from "./chat-ui";

export default function ChatPage() {
  // 用 calc(100vh-3rem) 减去 dashboard main 的 p-6（上下各 1.5rem = 3rem 总）
  // 让 chat 在不破坏左侧导航的前提下填满可视区
  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-3">
      <header className="shrink-0">
        <h1 className="text-xl font-semibold">对话参谋</h1>
        <p className="text-xs text-muted-foreground">
          DeepSeek-V4 + 6 个 tool · 所有金额来自后端 MILP 求解，绝不凭空生成
        </p>
      </header>
      <div className="flex-1 min-h-0">
        <ChatUI />
      </div>
    </div>
  );
}
