import React from "react";

// Minimal, dependency-free Markdown renderer for the chatbot's plausible output:
// **bold**, *italic*, `code`, headings (#..###), "-"/"*" bullet lists,
// "1." ordered lists, GFM pipe tables, and paragraphs. Not a full CommonMark
// implementation — just what the assistant actually emits. Keeps the app's
// no-UI-library ethos (no react-markdown / remark dependency tree).

interface Block {
  type: "p" | "h" | "ul" | "ol" | "table";
  level?: number;
  text?: string;
  items?: string[];
  header?: string[];
  rows?: string[][];
}

const splitRow = (line: string): string[] =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

const isUl = (l: string) => /^\s*[-*]\s+/.test(l);
const isOl = (l: string) => /^\s*\d+\.\s+/.test(l);
const isHeading = (l: string) => /^#{1,6}\s+/.test(l);
const isTableRow = (l: string) => /^\s*\|/.test(l);
const isTableSep = (l: string) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.includes("-");

function parse(text: string): Block[] {
  const lines = (text || "").replace(/\r/g, "").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) { rows.push(splitRow(lines[i])); i++; }
      blocks.push({ type: "table", header, rows });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) { blocks.push({ type: "h", level: h[1].length, text: h[2] }); i++; continue; }
    if (isUl(line)) {
      const items: string[] = [];
      while (i < lines.length && isUl(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
      blocks.push({ type: "ul", items });
      continue;
    }
    if (isOl(line)) {
      const items: string[] = [];
      while (i < lines.length && isOl(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      blocks.push({ type: "ol", items });
      continue;
    }
    const para = [line]; i++;
    while (i < lines.length && lines[i].trim() && !isTableRow(lines[i]) && !isHeading(lines[i]) && !isUl(lines[i]) && !isOl(lines[i])) {
      para.push(lines[i]); i++;
    }
    blocks.push({ type: "p", text: para.join("\n") });
  }
  return blocks;
}

// Inline: **bold**, *italic*, `code`.
function inline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let last = 0; let m: RegExpExecArray | null; let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] != null) nodes.push(<strong key={k++}>{m[2]}</strong>);
    else if (m[3] != null) nodes.push(<em key={k++}>{m[3]}</em>);
    else if (m[4] != null) nodes.push(<code key={k++} style={{ fontFamily: "var(--font-mono)", fontSize: "0.92em", background: "var(--bg-subtle)", padding: "1px 4px", borderRadius: 3 }}>{m[4]}</code>);
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const td: React.CSSProperties = { padding: "4px 10px", borderBottom: "1px solid var(--border)", fontSize: 13, whiteSpace: "nowrap", verticalAlign: "top" };
const th: React.CSSProperties = { ...td, textAlign: "left", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 500 };

export function Markdown({ text }: { text: string }) {
  const blocks = parse(text);
  return (
    <div style={{ fontSize: "var(--fs-body-sm)", lineHeight: "var(--lh-normal)" }}>
      {blocks.map((b, i) => {
        if (b.type === "h") {
          const size = b.level === 1 ? "var(--fs-h4)" : "var(--fs-body)";
          return <div key={i} style={{ fontWeight: 700, fontSize: size, margin: i === 0 ? "0 0 var(--space-2)" : "var(--space-3) 0 var(--space-2)" }}>{inline(b.text || "")}</div>;
        }
        if (b.type === "ul" || b.type === "ol") {
          const Tag = b.type === "ul" ? "ul" : "ol";
          return (
            <Tag key={i} style={{ margin: "var(--space-1) 0 var(--space-2)", paddingLeft: "var(--space-5)" }}>
              {(b.items || []).map((it, j) => <li key={j} style={{ marginBottom: 2 }}>{inline(it)}</li>)}
            </Tag>
          );
        }
        if (b.type === "table") {
          return (
            <div key={i} style={{ overflowX: "auto", margin: "var(--space-2) 0" }}>
              <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
                <thead><tr>{(b.header || []).map((c, j) => <th key={j} style={th}>{inline(c)}</th>)}</tr></thead>
                <tbody>
                  {(b.rows || []).map((r, j) => (
                    <tr key={j}>{r.map((c, k) => <td key={k} style={td}>{inline(c)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return <p key={i} style={{ margin: i === 0 ? "0 0 var(--space-2)" : "var(--space-2) 0", whiteSpace: "pre-wrap" }}>{inline(b.text || "")}</p>;
      })}
    </div>
  );
}
