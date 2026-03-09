export function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function inlineMarkdown(text) {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return out;
}

export function renderMarkdown(source) {
  const text = String(source || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return "<p>No Docling content available.</p>";
  const lines = text.split("\n");
  const blocks = [];
  let paragraph = [];
  let inCode = false;
  let codeLines = [];
  let listType = null;
  let listItems = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length && listType) {
      const tag = listType === "ol" ? "ol" : "ul";
      blocks.push(`<${tag}>${listItems.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${tag}>`);
      listItems = [];
      listType = null;
    }
  }

  function flushCode() {
    if (codeLines.length) {
      blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      codeLines = [];
    }
  }

  for (const rawLine of lines) {
    const line = rawLine || "";
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${inlineMarkdown(trimmed.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }
    const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const ordered = trimmed.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      flushParagraph();
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(ordered[1]);
      continue;
    }
    const unordered = trimmed.match(/^[-*]\s+(.*)$/);
    if (unordered) {
      flushParagraph();
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(unordered[1]);
      continue;
    }
    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  flushCode();
  return blocks.join("");
}
