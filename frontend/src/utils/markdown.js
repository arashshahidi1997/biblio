export function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function inlineMarkdown(text, { imageBase = "" } = {}) {
  // Process images first (before escaping), then escape non-image parts
  const imgRe = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const parts = [];
  let last = 0;
  let m;
  while ((m = imgRe.exec(text)) !== null) {
    parts.push(escapeHtml(text.slice(last, m.index)));
    const src = imageBase && !m[2].startsWith("http") && !m[2].startsWith("/")
      ? `${imageBase}/${m[2]}`
      : m[2];
    parts.push(`<img src="${escapeHtml(src)}" alt="${escapeHtml(m[1])}" style="max-width:100%;height:auto;">`);
    last = m.index + m[0].length;
  }
  parts.push(escapeHtml(text.slice(last)));
  let out = parts.join("");
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return out;
}

export function renderMarkdown(source, { imageBase = "" } = {}) {
  const text = String(source || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return "<p>No Docling content available.</p>";
  const lines = text.split("\n");
  const blocks = [];
  let paragraph = [];
  let inCode = false;
  let codeLines = [];
  let listType = null;
  let listItems = [];

  const inline = (t) => inlineMarkdown(t, { imageBase });

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length && listType) {
      const tag = listType === "ol" ? "ol" : "ul";
      blocks.push(`<${tag}>${listItems.map((item) => `<li>${inline(item)}</li>`).join("")}</${tag}>`);
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
    // Standalone image line → render as a block element
    if (trimmed.startsWith("![")) {
      flushParagraph();
      flushList();
      blocks.push(inline(trimmed));
      continue;
    }
    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${inline(trimmed.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }
    const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${inline(heading[2])}</h${level}>`);
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
