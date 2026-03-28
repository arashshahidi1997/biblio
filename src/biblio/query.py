"""Boolean query DSL for filtering papers by library + BibTeX metadata.

Grammar (case-insensitive operators)::

    expr     = or_expr
    or_expr  = and_expr ( 'OR' and_expr )*
    and_expr = not_expr ( 'AND' not_expr )*
    not_expr = 'NOT' not_expr | atom
    atom     = '(' expr ')' | predicate
    predicate = FIELD ':' VALUE

Supported predicates:
    tag:<value>          — matches any tag (including namespace:value)
    status:<value>       — matches library status
    priority:<value>     — matches library priority
    author:<substring>   — substring match on any author name
    year:<value>         — exact year match
    year:>N / year:<N / year:>=N / year:<=N — numeric comparison
    has:pdf / has:docling / has:grobid / has:notes — artifact existence
    type:<entrytype>     — BibTeX entry type (article, inproceedings, …)
    keyword:<value>      — BibTeX keywords field substring match
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── AST nodes ────────────────────────────────────────────────────────────────

@dataclass
class Predicate:
    field: str
    value: str

    def __repr__(self) -> str:
        return f"{self.field}:{self.value}"


@dataclass
class NotExpr:
    child: "Expr"

    def __repr__(self) -> str:
        return f"NOT({self.child!r})"


@dataclass
class AndExpr:
    children: list["Expr"] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"AND({', '.join(repr(c) for c in self.children)})"


@dataclass
class OrExpr:
    children: list["Expr"] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"OR({', '.join(repr(c) for c in self.children)})"


Expr = Predicate | NotExpr | AndExpr | OrExpr


# ── Tokenizer ────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \(                          # left paren
  | \)                          # right paren
  | (?:AND|OR|NOT)\b            # boolean operators (case-sensitive tokens, we upper-case input)
  | [A-Za-z_][A-Za-z0-9_]*     # bare word (field name or operator before uppercasing)
    :[^\s()]+                   # colon + value (no spaces/parens)
  | [A-Za-z_][A-Za-z0-9_]*     # bare word
    """,
    re.VERBOSE,
)

# Simpler: tokenize by splitting on whitespace, respecting parens
def _tokenize(query: str) -> list[str]:
    """Split query into tokens: parens, operators, and field:value predicates."""
    tokens: list[str] = []
    # Insert spaces around parens for easy splitting
    q = query.replace("(", " ( ").replace(")", " ) ")
    for part in q.split():
        if not part:
            continue
        tokens.append(part)
    return tokens


# ── Parser ───────────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, expected: str) -> None:
        tok = self.peek()
        if tok != expected:
            raise ParseError(f"Expected '{expected}', got '{tok}' at position {self.pos}")
        self.consume()

    def parse(self) -> Expr:
        expr = self._or_expr()
        if self.pos < len(self.tokens):
            raise ParseError(f"Unexpected token '{self.tokens[self.pos]}' at position {self.pos}")
        return expr

    def _or_expr(self) -> Expr:
        children = [self._and_expr()]
        while self.peek() and self.peek().upper() == "OR":
            self.consume()
            children.append(self._and_expr())
        return children[0] if len(children) == 1 else OrExpr(children)

    def _and_expr(self) -> Expr:
        children = [self._not_expr()]
        while self.peek() and self.peek().upper() == "AND":
            self.consume()
            children.append(self._not_expr())
        return children[0] if len(children) == 1 else AndExpr(children)

    def _not_expr(self) -> Expr:
        if self.peek() and self.peek().upper() == "NOT":
            self.consume()
            return NotExpr(self._not_expr())
        return self._atom()

    def _atom(self) -> Expr:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of query")
        if tok == "(":
            self.consume()
            expr = self._or_expr()
            self.expect(")")
            return expr
        if tok in (")", "AND", "OR", "NOT") or tok.upper() in ("AND", "OR", "NOT"):
            if tok == ")":
                raise ParseError(f"Unexpected ')' at position {self.pos}")
            raise ParseError(f"Unexpected operator '{tok}' at position {self.pos}")
        # Must be a predicate: field:value
        self.consume()
        if ":" not in tok:
            raise ParseError(f"Expected field:value predicate, got '{tok}'")
        field_name, _, value = tok.partition(":")
        return Predicate(field=field_name.lower(), value=value)


def parse_query(query: str) -> Expr:
    """Parse a boolean query string into an AST."""
    tokens = _tokenize(query)
    if not tokens:
        raise ParseError("Empty query")
    return _Parser(tokens).parse()


# ── Evaluator ────────────────────────────────────────────────────────────────

def _match_predicate(pred: Predicate, library_entry: dict[str, Any], bib_entry: dict[str, Any]) -> bool:
    """Evaluate a single predicate against a paper's metadata."""
    f = pred.field
    v = pred.value

    if f == "tag":
        tags: list[str] = library_entry.get("tags") or []
        v_lower = v.lower()
        return any(v_lower == t.lower() for t in tags)

    if f == "status":
        return (library_entry.get("status") or "").lower() == v.lower()

    if f == "priority":
        return (library_entry.get("priority") or "").lower() == v.lower()

    if f == "author":
        authors: list[str] = bib_entry.get("authors") or []
        v_lower = v.lower()
        return any(v_lower in a.lower() for a in authors)

    if f == "year":
        paper_year_str = bib_entry.get("year") or library_entry.get("year") or ""
        try:
            paper_year = int(str(paper_year_str))
        except (ValueError, TypeError):
            return False
        # Comparison operators
        if v.startswith(">="):
            return paper_year >= int(v[2:])
        if v.startswith("<="):
            return paper_year <= int(v[2:])
        if v.startswith(">"):
            return paper_year > int(v[1:])
        if v.startswith("<"):
            return paper_year < int(v[1:])
        return paper_year == int(v)

    if f == "has":
        # Check artifact existence flags (set by caller)
        artifacts: dict[str, bool] = library_entry.get("_artifacts") or {}
        return artifacts.get(v.lower(), False)

    if f == "type":
        entry_type = bib_entry.get("type") or ""
        return entry_type.lower() == v.lower()

    if f == "keyword":
        kw_str = bib_entry.get("keywords") or bib_entry.get("keyword") or ""
        return v.lower() in kw_str.lower()

    return False


def evaluate(expr: Expr, library_entry: dict[str, Any], bib_entry: dict[str, Any]) -> bool:
    """Evaluate a parsed query expression against a single paper's metadata."""
    if isinstance(expr, Predicate):
        return _match_predicate(expr, library_entry, bib_entry)
    if isinstance(expr, NotExpr):
        return not evaluate(expr.child, library_entry, bib_entry)
    if isinstance(expr, AndExpr):
        return all(evaluate(c, library_entry, bib_entry) for c in expr.children)
    if isinstance(expr, OrExpr):
        return any(evaluate(c, library_entry, bib_entry) for c in expr.children)
    raise TypeError(f"Unknown expression type: {type(expr)}")


def query_citekeys(
    query_str: str,
    library: dict[str, dict[str, Any]],
    bib_entries: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Filter citekeys by a query string. Returns matching citekey list.

    ``library`` is the full library.yml dict (citekey -> entry).
    ``bib_entries`` is an optional dict of citekey -> bib metadata dict
    (with 'authors', 'year', 'type', 'keywords' fields).
    """
    expr = parse_query(query_str)
    bib = bib_entries or {}
    # Collect all known citekeys from both sources
    all_keys = sorted(set(library.keys()) | set(bib.keys()))
    return [
        k for k in all_keys
        if evaluate(expr, library.get(k, {}), bib.get(k, {}))
    ]
