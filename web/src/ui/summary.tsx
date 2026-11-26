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
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: line.slice(3) });
      continue;
    }
    if (line.startsWith("- ")) {
      flushParagraph();
      list.push(line.slice(2));
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
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
