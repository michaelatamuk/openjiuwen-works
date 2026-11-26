import type { ReactNode } from "react";

type Block =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

function inline(text: string): ReactNode[] {
  return text.split("`").map((part, index) =>
    index % 2 ? <code key={index}>{part}</code> : <span key={index}>{part}</span>,
  );
}

function parse(text: string): Block[] {
  return text
    .trim()
    .split(/\n{2,}/)
    .map((group) => group.trim())
    .filter(Boolean)
    .flatMap<Block>((group) => {
      const lines = group.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.length === 1 && lines[0].startsWith("## ")) {
        return [{ kind: "heading", text: lines[0].slice(3) }];
      }
      if (lines.every((line) => line.startsWith("- "))) {
        return [{ kind: "list", items: lines.map((line) => line.slice(2)) }];
      }
      return [{ kind: "paragraph", text: lines.join(" ") }];
    });
}

export type SummaryTextProps = {
  text?: string | null;
};

export function SummaryText({ text }: SummaryTextProps) {
  const blocks = parse(text || "");
  if (!blocks.length) {
    return <p className="muted small">No summary recorded.</p>;
  }
  return (
    <div className="summary">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return <h3 key={index}>{block.text}</h3>;
        }
        if (block.kind === "list") {
          return (
            <ul key={index} className="bullets">
              {block.items.map((item) => <li key={item}>{inline(item)}</li>)}
            </ul>
          );
        }
        return <p key={index}>{inline(block.text)}</p>;
      })}
    </div>
  );
}
