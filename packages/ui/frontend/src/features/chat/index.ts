// Barrel for the chat feature module.
// Consumers import from "@/features/chat" rather than reaching into the
// individual files. Keeps the public surface explicit and discoverable.

export { useChatSession } from "./use-chat-session";
export type { UseChatSessionOptions, UseChatSessionReturn } from "./use-chat-session";

export type {
  ChatStatus,
  ConsequenceChoice,
  DiceRequest,
  SendOptions,
  StreamingMessage,
  ThinkingTrace,
  TurnFailure,
  WsClientMsg,
  WsServerMsg,
} from "./types";

export { ChatList } from "./ChatList";
export type { ChatListProps } from "./ChatList";

export { Composer } from "./Composer";
export type { ComposerProps, QuickAction } from "./Composer";

export { ConsequenceBanner } from "./ConsequenceBanner";
export { CopyButton } from "./CopyButton";
export { DiceResultCard } from "./DiceResultCard";
export { DiceRollPrompt } from "./DiceRollPrompt";
export { ProseBubble } from "./ProseBubble";
export { StatusPill } from "./StatusPill";
export { ThinkingBubble } from "./ThinkingBubble";
export type { ThinkingBubbleProps } from "./ThinkingBubble";
export { TypingIndicator } from "./TypingIndicator";