#!/usr/bin/env python3
"""verify_page.py — double-checks a web page someone else (an AI agent) built.

    python3 verify_page.py <index.html or folder> [--content content.md] [--facts facts.json] [--live https://url] [--out receipts/]

It never edits the page. It runs six checks, writes a markdown receipt to receipts/,
and exits 1 if anything FAILed (0 if only PASS/WARN, 2 if it could not start).
Python 3 standard library only. The render check needs Chrome or Chromium: set CHROME=/path/to/chrome
if it is not at the macOS default path or on your PATH.
"""
import argparse
import concurrent.futures
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

KIT = os.path.dirname(os.path.abspath(__file__))
CHROME = (os.environ.get("CHROME")
          or next((p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",) if os.path.isfile(p)), None)
          or next((shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(n)), None)
          or "chrome-not-found")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0 Safari/537.36 verify_page/1.0")
TIMEOUT = 12
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
RANK = {PASS: 0, WARN: 1, FAIL: 2}

# --------------------------------------------------------------------------- text helpers

URLISH = re.compile(r"\S*(?:https?://|www\.|@|/)\S*|\S+\.(?:com|io|org|net|dev|app|co|ai)\b\S*", re.I)
NUM = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?:%|\+|k|K|M|x|st|nd|rd|th)?(?![\w])")
PAIR = re.compile(r"(?<![\w.,])(\d[\d,]*)\s+(?:of|out of)\s+(\d[\d,]*)(?![\w])")
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,4})\b")
NUMBER_WORDS = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy "
                "eighty ninety hundred thousand dozen").split()
NUMWORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)


def strip_urls(text):
    return URLISH.sub(" ", text)


def norm_num(tok):
    return tok.replace(",", "")


def extract_numbers(text):
    return [norm_num(m.group(0)) for m in NUM.finditer(strip_urls(text))]


def extract_pairs(text):
    return {f"{norm_num(a)} of {norm_num(b)}" for a, b in PAIR.findall(strip_urls(text))}


def extract_dates(text):
    return {f"{mon.lower()} {num}" for mon, num in DATE.findall(text)}


def extract_number_words(text):
    return {w.lower() for w in NUMWORD.findall(strip_urls(text))}


def norm_sentence(s):
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"[*_`#]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


# --------------------------------------------------------------------------- HTML parsing

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
OPTIONAL_END = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot", "option", "optgroup",
                "colgroup", "rt", "rp", "html", "head", "body"}
BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header",
         "footer", "main", "nav", "br", "tr", "td", "th", "table", "blockquote", "pre", "dt", "dd", "aside",
         "figure", "figcaption", "title", "address", "hr"}
HIDDEN = {"script", "style", "template", "noscript", "svg"}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doctype = None
        self.html_lang = None
        self.title = None
        self._in_title = False
        self.viewport = None
        self.h1 = []
        self._h1_buf = None
        self.imgs = []          # (line, attrs)
        self.scripts = []       # (line, src or None)
        self.stylesheets = []   # (line, href)
        self.hrefs = []         # (line, tag, attrs)
        self.srcs = []          # (line, tag, src)
        self.ids = set()
        self.text = []          # visible text pieces
        self.extra_text = []    # title, alt, meta description (also fact-checked)
        self.stack = []         # (tag, line)
        self.tag_errors = []    # (line, message)
        self._hidden_depth = 0
        self.inline_styles = []  # (tag, style)
        self.style_blocks = []
        self._in_style = False

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.doctype = decl

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        line = self.getpos()[0]
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and "name" in a:
            self.ids.add(a["name"])
        if a.get("style"):
            self.inline_styles.append((tag, a["style"]))
        if tag == "html":
            self.html_lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
            self.title = ""
        elif tag == "meta":
            if a.get("name", "").lower() == "viewport":
                self.viewport = a.get("content", "")
            if a.get("name", "").lower() == "description":
                self.extra_text.append(a.get("content", ""))
        elif tag == "h1":
            self._h1_buf = ""
        elif tag == "img":
            self.imgs.append((line, a))
            if "alt" in a:
                self.extra_text.append(a["alt"])
        elif tag == "script":
            self.scripts.append((line, a.get("src")))
        elif tag == "style":
            self._in_style = True
        if tag == "link" and "stylesheet" in a.get("rel", "").lower():
            self.stylesheets.append((line, a.get("href", "")))
        if "href" in a and tag in ("a", "link", "area"):
            self.hrefs.append((line, tag, a))
        if "src" in a and tag in ("img", "script", "iframe", "source", "video", "audio", "embed"):
            self.srcs.append((line, tag, a["src"]))
        if tag in HIDDEN:
            self._hidden_depth += 1
        if tag in BLOCK:
            self.text.append("\n")
        if tag not in VOID:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
            if tag in HIDDEN:
                self._hidden_depth -= 1

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag == "title":
            self._in_title = False
        elif tag == "h1" and self._h1_buf is not None:
            self.h1.append(self._h1_buf.strip())
            self._h1_buf = None
        elif tag == "style":
            self._in_style = False
        if tag in HIDDEN and self._hidden_depth > 0:
            self._hidden_depth -= 1
        if tag in BLOCK:
            self.text.append("\n")
        if tag in VOID:
            return
        names = [t for t, _ in self.stack]
        if tag not in names:
            self.tag_errors.append((line, f"</{tag}> closes nothing (stray or mismatched end tag)"))
            return
        while self.stack:
            t, l = self.stack.pop()
            if t == tag:
                break
            if t not in OPTIONAL_END:
                self.tag_errors.append((l, f"<{t}> opened on line {l} is never closed (closed early by </{tag}> on line {line})"))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_style:
            self.style_blocks.append(data)
        if self._h1_buf is not None:
            self._h1_buf += data
        if self._hidden_depth == 0 and not self._in_title:
            self.text.append(data)

    def finish(self):
        self.close()
        for t, l in self.stack:
            if t not in OPTIONAL_END:
                self.tag_errors.append((l, f"<{t}> opened on line {l} is never closed"))
        if self.title:
            self.extra_text.insert(0, self.title)

    def visible_text(self):
        return re.sub(r"[ \t\r\f\v]+", " ", "".join(self.text))


# --------------------------------------------------------------------------- results

class Check:
    def __init__(self, num, name):
        self.num, self.name = num, name
        self.items = []  # (level, code, message)

    def add(self, level, code, msg):
        self.items.append((level, code, msg))

    @property
    def result(self):
        if not self.items:
            return PASS
        return max((lvl for lvl, _, _ in self.items), key=RANK.get)

    def count(self, level):
        return sum(1 for lvl, _, _ in self.items if lvl == level)


# --------------------------------------------------------------------------- check 1: facts

def check_facts(p, facts):
    c = Check(1, "Facts (numbers and claims vs allow-list)")
    manual = facts.get("manual") if isinstance(facts.get("manual"), dict) else {}
    allowed_nums = set(facts.get("numbers", {})) | set((manual.get("numbers") or {}))
    allowed_pairs = set(facts.get("of_pairs", [])) | set(manual.get("of_pairs") or [])
    allowed_dates = set(facts.get("dates", [])) | set(manual.get("dates") or [])
    allowed_words = set(facts.get("number_words", []))
    stale = facts.get("stale", {}) or {}

    body = p.visible_text()
    everything = body + "\n" + "\n".join(p.extra_text)
    lines = everything.split("\n")

    def where(token_re):
        """The words around the first match, so you can find it on the page."""
        for ln in lines:
            m = re.search(token_re, strip_urls(ln))
            if m:
                s = strip_urls(ln)
                lo, hi = max(0, m.start() - 60), min(len(s), m.end() + 60)
                return ("..." if lo else "") + s[lo:hi].strip() + ("..." if hi < len(s) else "")
        return ""

    found = extract_numbers(everything)
    seen = set()
    for n in found:
        if n in seen:
            continue
        seen.add(n)
        if n not in allowed_nums:
            # show the line, matching with or without thousands commas
            pat = r"(?<![\w.,])" + r",?".join(re.escape(ch) for ch in n) + r"(?![\w])"
            c.add(FAIL, "FACT_NUMBER", f"number `{n}` is not in the allow-list. Seen in: \"{where(pat)}\"")
    for pair in sorted(extract_pairs(everything)):
        if pair in stale:
            c.add(FAIL, "FACT_STALE", f"`{pair}` is a known-wrong figure: {stale[pair]}")
        elif pair not in allowed_pairs:
            c.add(FAIL, "FACT_PAIR", f"`{pair}` is not an allowed 'X of Y' figure (allowed: {', '.join(sorted(allowed_pairs)) or 'none'})")
    for d in sorted(extract_dates(everything)):
        if d not in allowed_dates:
            c.add(FAIL, "FACT_DATE", f"date `{d}` does not appear in the sources")
    for w in sorted(extract_number_words(everything)):
        if w not in allowed_words:
            ctx = where(r"(?i)\b" + w + r"\b")
            c.add(WARN, "FACT_NUMWORD", f"spelled-out number `{w}` is not in the sources (check it is not an inflated claim): \"{ctx}\"")
    for req in facts.get("required_text", []):
        if req not in everything:
            c.add(FAIL, "FACT_REQUIRED_TEXT", f"`{req}` (exact spelling) does not appear on the page")
    for bad in facts.get("banned_spellings", []):
        if re.search(r"\b" + re.escape(bad) + r"\b", everything):
            c.add(FAIL, "FACT_SPELLING", f"wrong spelling `{bad}` appears (should be `{', '.join(facts.get('required_text', []))}`)")
    for name in facts.get("banned_names", []):
        if re.search(r"\b" + re.escape(name) + r"\b", everything, re.I):
            ctx = where(r"(?i)" + re.escape(name))
            c.add(FAIL, "FACT_BANNED_NAME", f"banned name `{name}` appears: \"{ctx}\"")
    for bc in facts.get("banned_claims", []):
        m = re.search(bc["pattern"], everything, re.I)
        if m:
            c.add(FAIL, "FACT_BANNED_CLAIM", f"banned claim ({bc['label']}): \"{m.group(0)}\"")

    # Sentence-level: anything not word-for-word in the source text. WARN only (rewording is normal).
    src = norm_sentence(facts.get("source_text", ""))
    if src:
        unmatched = []
        for sent in re.split(r"(?<=[.!?])\s+|\n", everything):
            s = norm_sentence(sent)
            if len(s.split()) >= 4 and s not in src:
                unmatched.append(sent.strip())
        for s in unmatched[:25]:
            c.add(WARN, "FACT_SENTENCE", f"sentence not word-for-word in the source text, read it: \"{s[:160]}\"")
        if len(unmatched) > 25:
            c.add(WARN, "FACT_SENTENCE", f"...and {len(unmatched) - 25} more unmatched sentences")
    c.evidence = f"{len(seen)} distinct numbers checked: {', '.join(sorted(seen, key=lambda x: (len(x), x)))[:600] or 'none'}"
    return c


# --------------------------------------------------------------------------- check 2: links

def safe_url(url):
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    netloc = host + (f":{parts.port}" if parts.port else "")
    path = urllib.parse.quote(parts.path, safe="/%:@&=+$,;~!*'()-._")
    query = urllib.parse.quote(parts.query, safe="/%:@&=+$,;~!*'()-._?")
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, ""))


def fetch_status(url):
    """HEAD, falling back to GET. Returns (status or None, method, detail)."""
    u = safe_url(url)
    last = None
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(u, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                final = r.geturl()
                detail = f"redirected to {final}" if final.rstrip("/") != u.rstrip("/") else ""
                return r.status, method, detail
        except urllib.error.HTTPError as e:
            last = (e.code, method, "")
            if method == "HEAD" and e.code in (400, 403, 404, 405, 429, 500, 501, 503, 999):
                continue  # many servers answer HEAD badly; confirm with GET
            return last
        except Exception as e:  # DNS, timeout, TLS
            last = (None, method, f"{type(e).__name__}: {e}")
            continue
    return last


def check_links(p, page_path, facts):
    c = Check(2, "Links")
    base_dir = os.path.dirname(page_path)
    email = (facts.get("email") or "").lower()
    external = {}
    rows = []
    for line, tag, a in p.hrefs:
        href = a.get("href", "").strip()
        label = f"line {line} <{tag}> href=\"{href}\""
        if not href:
            c.add(FAIL, "LINK_EMPTY", f"{label}: empty link")
            continue
        low = href.lower()
        if low.startswith("mailto:"):
            addr = urllib.parse.unquote(href[7:].split("?")[0]).strip().lower()
            if email and addr != email:
                c.add(FAIL, "LINK_MAILTO", f"{label}: email is `{addr}`, must be `{email}`")
            else:
                rows.append(f"{label}: mailto OK")
            continue
        if low.startswith("tel:"):
            rows.append(f"{label}: phone link (not checked)")
            continue
        if low.startswith("javascript:"):
            c.add(WARN, "LINK_JS", f"{label}: javascript: link")
            continue
        if href == "#":
            c.add(WARN, "LINK_PLACEHOLDER", f"{label}: placeholder '#' link goes nowhere")
            continue
        if href.startswith("#"):
            if urllib.parse.unquote(href[1:]) in p.ids:
                rows.append(f"{label}: anchor target exists")
            else:
                c.add(FAIL, "LINK_ANCHOR", f"{label}: no element with id `{href[1:]}` on the page")
            continue
        if low.startswith(("http://", "https://", "//")):
            url = ("https:" + href) if href.startswith("//") else href
            external.setdefault(url, []).append(label)
            if tag == "a":
                target = a.get("target", "")
                rel = a.get("rel", "").lower().split()
                if target != "_blank":
                    c.add(FAIL, "LINK_TARGET", f"{label}: external link does not open in a new tab (needs target=\"_blank\")")
                if "noopener" not in rel:
                    if "noreferrer" in rel:
                        c.add(WARN, "LINK_REL", f"{label}: has rel=\"noreferrer\" (implies noopener in modern browsers) but not \"noopener\"")
                    else:
                        c.add(FAIL, "LINK_REL", f"{label}: external link missing rel=\"noopener\"")
            if low.startswith("http://") and not re.match(r"http://(127\.0\.0\.1|localhost)", low):
                c.add(WARN, "LINK_HTTP", f"{label}: plain http:// link (use https://)")
            continue
        # relative/local file
        local = urllib.parse.unquote(urllib.parse.urlsplit(href).path)
        target = os.path.normpath(os.path.join(base_dir, local))
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if os.path.exists(target):
            rows.append(f"{label}: local file exists")
        else:
            c.add(FAIL, "LINK_LOCAL_MISSING", f"{label}: local file not found ({target})")
    for line, tag, src in p.srcs:
        if src.lower().startswith(("http://", "https://", "//", "data:")):
            continue
        target = os.path.normpath(os.path.join(base_dir, urllib.parse.unquote(urllib.parse.urlsplit(src).path)))
        if not os.path.exists(target):
            c.add(FAIL, "LINK_LOCAL_MISSING", f"line {line} <{tag}> src=\"{src}\": file not found")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = dict(zip(external, ex.map(fetch_status, external)))
    for url, (status, method, detail) in results.items():
        where = "; ".join(external[url])
        ev = f"{url} -> {status if status is not None else 'no response'} via {method}" + (f" ({detail})" if detail else "")
        if status is not None and 200 <= status < 400:
            rows.append(ev + " OK")
        elif status == 999:
            c.add(WARN, "LINK_999", f"{ev}. LinkedIn blocks robots with 999; open it yourself in a browser. [{where}]")
        elif status == 429:
            c.add(WARN, "LINK_RATE_LIMIT", f"{ev}. Rate-limited; open it yourself. [{where}]")
        else:
            c.add(FAIL, "LINK_BROKEN", f"{ev} [{where}]")
    c.evidence = "\n".join(rows) if rows else "no working links recorded"
    c.evidence = f"{len(p.hrefs)} hrefs, {len(external)} distinct external URLs fetched.\n" + c.evidence
    return c


# --------------------------------------------------------------------------- check 3: HTML basics

def check_html(p):
    c = Check(3, "HTML basics")
    ev = []
    if not p.doctype or p.doctype.strip().lower() != "doctype html":
        c.add(FAIL, "HTML_DOCTYPE", f"missing or wrong <!doctype html> (found: {p.doctype!r})")
    else:
        ev.append("doctype html: yes")
    if not p.html_lang:
        c.add(FAIL, "HTML_LANG", "<html> has no lang attribute (screen readers need it)")
    else:
        ev.append(f"html lang: {p.html_lang}")
    if not (p.title or "").strip():
        c.add(FAIL, "HTML_TITLE", "missing or empty <title>")
    else:
        ev.append(f"title: {p.title.strip()!r}")
    if p.viewport is None:
        c.add(FAIL, "HTML_VIEWPORT", "missing <meta name=\"viewport\">; phones will show a tiny zoomed-out desktop page")
    elif "width=device-width" not in p.viewport.replace(" ", ""):
        c.add(WARN, "HTML_VIEWPORT", f"viewport is {p.viewport!r}, expected width=device-width")
    else:
        ev.append(f"viewport: {p.viewport}")
    if len(p.h1) != 1:
        c.add(FAIL, "HTML_H1", f"expected exactly one <h1>, found {len(p.h1)}: {p.h1}")
    else:
        ev.append(f"h1: {p.h1[0]!r}")
    for line, a in p.imgs:
        if "alt" not in a:
            c.add(FAIL, "HTML_IMG_ALT", f"line {line} <img src=\"{a.get('src', '')}\"> has no alt text")
    missing_alt = sum(1 for _, a in p.imgs if "alt" not in a)
    ev.append(f"images: {len(p.imgs)}, missing alt: {missing_alt}")
    for line, src in p.scripts:
        if src and src.strip().lower().startswith(("http://", "https://", "//")):
            c.add(FAIL, "HTML_EXTERNAL_SCRIPT", f"line {line} <script src=\"{src}\"> loads code from another site (page must be self-contained)")
    inline = [line for line, src in p.scripts if not src]
    if inline:
        c.add(WARN, "HTML_INLINE_SCRIPT", f"{len(inline)} inline <script> block(s) at line(s) {inline}; the project rules say no JavaScript")
    for line, href in p.stylesheets:
        if href.strip().lower().startswith(("http://", "https://", "//")):
            c.add(WARN, "HTML_EXTERNAL_CSS", f"line {line} stylesheet from another site: {href}")
    for line, msg in p.tag_errors:
        c.add(FAIL, "HTML_TAGS", f"line {line}: {msg}")
    if not p.tag_errors:
        ev.append("tags: no unclosed or mismatched tags (html.parser)")
    c.evidence = "\n".join(ev)
    return c


# --------------------------------------------------------------------------- check 4 + 5: render & contrast

MEASURE_JS = r"""
(function(){
 function rgb(s){var m=s.match(/rgba?\(([^)]+)\)/);if(!m)return null;var p=m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat);return [p[0],p[1],p[2],p.length>3?p[3]:1];}
 function bgOf(el,w){while(el){var cs=w.getComputedStyle(el);if(cs.backgroundImage&&cs.backgroundImage!=='none')return {img:true};var c=rgb(cs.backgroundColor);if(c&&c[3]>0.5)return {c:c};el=el.parentElement;}return {c:[255,255,255,1]};}
 function run(){
  var f=document.getElementById('__vf__'),w=f.contentWindow,d=w.document,de=d.documentElement,b=d.body,out={};
  out.innerWidth=w.innerWidth;out.clientWidth=de.clientWidth;
  out.scrollWidth=Math.max(de.scrollWidth,b?b.scrollWidth:0);
  out.text=b?(b.innerText||'').trim().length:0;
  out.textSample=b?(b.innerText||'').trim().slice(0,160):'';
  var wide=[],pairs={};
  var all=d.body?d.body.querySelectorAll('*'):[];
  for(var i=0;i<all.length;i++){var el=all[i],r=el.getBoundingClientRect();
   if(r.width>0&&r.right>w.innerWidth+1&&wide.length<8){wide.push({tag:el.tagName.toLowerCase(),id:el.id,cls:(el.className&&el.className.baseVal===undefined)?String(el.className):'',right:Math.round(r.right),width:Math.round(r.width)});}
   var own='';for(var k=0;k<el.childNodes.length;k++){if(el.childNodes[k].nodeType===3)own+=el.childNodes[k].textContent;}
   own=own.trim();if(!own||r.width===0)continue;
   var cs=w.getComputedStyle(el);if(cs.visibility==='hidden'||cs.display==='none')continue;
   var fs=parseFloat(cs.fontSize),fw=parseInt(cs.fontWeight,10)||400,large=fs>=24||(fs>=18.66&&fw>=700);
   var fg=rgb(cs.color),bg=bgOf(el,w),key=cs.color+'|'+(bg.img?'image':bg.c.join(','))+'|'+large;
   if(!pairs[key])pairs[key]={fg:fg,bg:bg.img?null:bg.c,tag:el.tagName.toLowerCase(),size:cs.fontSize,weight:cs.fontWeight,large:large,sample:own.slice(0,50),n:0};
   pairs[key].n++;}
  out.wide=wide;out.pairs=Object.keys(pairs).map(function(k){return pairs[k];});
  var pre=document.createElement('pre');pre.id='__verify_result__';pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
 }
 var f=document.getElementById('__vf__');
 f.addEventListener('load',function(){setTimeout(function(){try{run();}catch(e){var pre=document.createElement('pre');pre.id='__verify_result__';pre.textContent=JSON.stringify({error:String(e)});document.body.appendChild(pre);}},300);});
})();
"""


def wrapper_html(page_name, width, height, measure):
    script = f"<script>{MEASURE_JS}</script>" if measure else ""
    return (f"<!doctype html><html><head><meta charset=utf-8></head><body style=\"margin:0;overflow:hidden\">"
            f"<iframe id=\"__vf__\" src=\"{urllib.parse.quote(page_name)}\" "
            f"style=\"display:block;border:0;width:{width}px;height:{height}px\"></iframe>{script}</body></html>")


def run_chrome(args, timeout=90):
    profile = tempfile.mkdtemp(prefix="vp-chrome-")
    try:
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", "--allow-file-access-from-files",
               f"--user-data-dir={profile}"] + args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def luminance(c):
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(fg, bg):
    if fg is not None and len(fg) > 3 and fg[3] < 1 and bg is not None:  # blend translucent text
        a = fg[3]
        fg = [fg[i] * a + bg[i] * (1 - a) for i in range(3)]
    l1, l2 = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def check_render(page_path, out_dir, stamp):
    """Returns (render Check, measurements dict or None)."""
    c = Check(4, "Render (headless Chrome)")
    ev = []
    if not os.path.isfile(CHROME):
        c.add(FAIL, "RENDER_NO_CHROME", f"Chrome not found at {CHROME}; render could not run")
        c.evidence = ""
        return c, None
    work = tempfile.mkdtemp(prefix="vp-render-")
    try:
        # Copy the page's folder so the wrapper sits next to it (relative CSS/images still work).
        site = os.path.join(work, "site")
        src_dir = os.path.dirname(page_path)
        skip = shutil.ignore_patterns(".git", "node_modules", "receipts")
        n_files = sum(len(files) for _, _, files in os.walk(src_dir))
        if n_files <= 2000:
            shutil.copytree(src_dir, site, ignore=skip)
        else:  # pointed at a huge folder (e.g. Downloads): copy only its top-level files
            os.makedirs(site)
            for fn in os.listdir(src_dir):
                if os.path.isfile(os.path.join(src_dir, fn)):
                    shutil.copy2(os.path.join(src_dir, fn), site)
            c.add(WARN, "RENDER_BIG_FOLDER", f"{src_dir} has {n_files} files; copied only its top-level files to render. Put the page in its own folder.")
        name = os.path.basename(page_path)

        # Screenshots. Chrome clamps headless windows to >=500px, so a plain --window-size=390
        # screenshot is really a 500px layout cropped to 390. Wrapping the page in a 390px iframe
        # gives a true 390px layout (verified 2026-10-22). 1280 is above the clamp; same method for parity.
        shots = {}
        for w, h in ((390, 1800), (1280, 1800)):
            wrap = os.path.join(site, f"__vp_wrap_{w}.html")
            with open(wrap, "w", encoding="utf-8") as f:
                f.write(wrapper_html(name, w, h, measure=False))
            png = os.path.join(out_dir, f"shot-{stamp}-{w}px.png")
            r = run_chrome([f"--window-size={w},{h}", "--virtual-time-budget=4000", f"--screenshot={png}",
                            "file://" + wrap])
            size = png_size(png) if os.path.isfile(png) else None
            if not size:
                c.add(FAIL, "RENDER_SCREENSHOT", f"{w}px screenshot not produced. chrome exit {r.returncode}: {r.stderr.strip()[-300:]}")
            else:
                shots[w] = png
                ev.append(f"screenshot {w}px: {os.path.basename(png)} (PNG {size[0]}x{size[1]})")

        # Overflow at 390px and 320px. An injected script
        # measures the framed page and writes JSON into the DOM, which --dump-dom prints.
        data = None
        for width in (390, 320):
            wrap = os.path.join(site, f"__vp_measure_{width}.html")
            with open(wrap, "w", encoding="utf-8") as f:
                f.write(wrapper_html(name, width, 844, measure=True))
            r = run_chrome(["--window-size=1280,900", "--virtual-time-budget=5000", "--dump-dom", "file://" + wrap])
            m = re.search(r'<pre id="__verify_result__">(.*?)</pre>', r.stdout, re.S)
            d = None
            if m:
                try:
                    d = json.loads(html.unescape(m.group(1)))
                except ValueError:
                    d = None
            if not isinstance(d, dict) or "error" in d:
                why = d.get("error") if isinstance(d, dict) else "no result in dumped DOM"
                c.add(FAIL, "RENDER_MEASURE", f"could not measure the page in Chrome at {width}px: {why}")
                continue
            if width == 390:
                data = d
            ev.append(f"measured at {width}px: innerWidth={d['innerWidth']} clientWidth={d['clientWidth']} scrollWidth={d['scrollWidth']}")
            if d["innerWidth"] != width:
                c.add(WARN, "RENDER_WIDTH_UNRELIABLE", f"Chrome laid out at {d['innerWidth']}px, not {width}px; overflow result not trustworthy")
            if width == 390:
                if d["text"] <= 0:
                    c.add(FAIL, "RENDER_EMPTY", "page renders with no visible text")
                else:
                    ev.append(f"visible text: {d['text']} characters, starts: {d['textSample'][:80]!r}")
            if d["scrollWidth"] > d["clientWidth"] + 1:
                culprits = ", ".join(f"<{w_['tag']}{'#' + w_['id'] if w_['id'] else ''}{'.' + w_['cls'].split()[0] if w_['cls'].strip() else ''}> right edge {w_['right']}px"
                                     for w_ in d["wide"]) or "unknown element"
                c.add(FAIL, "RENDER_OVERFLOW", f"page scrolls sideways on a {width}px phone: content is {d['scrollWidth']}px wide. Widest: {culprits}")
            elif d["wide"]:
                culprits = ", ".join(f"<{w_['tag']}> right edge {w_['right']}px" for w_ in d["wide"])
                c.add(WARN, "RENDER_CLIPPED", f"at {width}px no sideways scroll, but elements extend past the edge and may be cut off: {culprits}")
            else:
                ev.append(f"no horizontal overflow at {width}px")
        c.evidence = "\n".join(ev)
        c.shots = shots
        return c, data
    except subprocess.TimeoutExpired:
        c.add(FAIL, "RENDER_TIMEOUT", "Chrome did not finish within 90 seconds")
        c.evidence = "\n".join(ev)
        return c, None
    finally:
        shutil.rmtree(work, ignore_errors=True)


NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "gray": (128, 128, 128),
         "grey": (128, 128, 128), "silver": (192, 192, 192), "navy": (0, 0, 128), "blue": (0, 0, 255),
         "yellow": (255, 255, 0), "transparent": None}


def parse_css_color(v, variables):
    v = v.strip().lower()
    m = re.match(r"var\((--[\w-]+)", v)
    if m:
        return parse_css_color(variables.get(m.group(1), ""), variables)
    m = re.match(r"#([0-9a-f]{3,8})\b", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [1]
    m = re.match(r"rgba?\(([^)]+)\)", v)
    if m:
        p = [x for x in re.split(r"[ ,/]+", m.group(1)) if x]
        return [float(x) for x in p[:3]] + [float(p[3]) if len(p) > 3 else 1]
    return list(NAMED[v]) + [1] if NAMED.get(v) else None


def css_fallback_colors(p):
    """Best-effort: read body/html/:root color + background from <style> and inline styles."""
    css = "\n".join(p.style_blocks)
    variables = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", css))
    fg = bg = None
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        names = [s.strip() for s in sel.split(",")]
        if any(n in ("body", "html", ":root") for n in names):
            for prop, val in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body):
                if prop == "color":
                    fg = parse_css_color(val, variables) or fg
                elif prop in ("background", "background-color"):
                    bg = parse_css_color(val, variables) or bg
    for tag, style in p.inline_styles:
        if tag in ("body", "html"):
            for prop, val in re.findall(r"([\w-]+)\s*:\s*([^;]+)", style):
                if prop == "color":
                    fg = parse_css_color(val, variables) or fg
                elif prop in ("background", "background-color"):
                    bg = parse_css_color(val, variables) or bg
    return fg or [0, 0, 0, 1], bg or [255, 255, 255, 1]


def check_contrast(p, measured):
    c = Check(5, "Contrast (best effort, WARN-only)")
    ev = []
    if measured and measured.get("pairs"):
        ev.append("method: colors Chrome actually computed for every element with its own text (at 390px)")
        for pr in measured["pairs"]:
            if pr["bg"] is None:
                c.add(WARN, "CONTRAST_IMAGE_BG", f"<{pr['tag']}> \"{pr['sample']}\" sits on a background image; check contrast by eye")
                continue
            if not pr["fg"]:
                continue
            ratio = contrast(pr["fg"], pr["bg"])
            need = 3.0 if pr.get("large") else 4.5
            fg = "rgb(" + ",".join(str(round(x)) for x in pr["fg"][:3]) + ")"
            bg = "rgb(" + ",".join(str(round(x)) for x in pr["bg"][:3]) + ")"
            line = f"<{pr['tag']}> {fg} on {bg}: {ratio:.2f}:1 (needs {need}, {pr['size']} {'large' if pr.get('large') else 'normal'} text, {pr['n']} element(s)) e.g. \"{pr['sample']}\""
            if ratio < need:
                c.add(WARN, "CONTRAST_LOW", line)
            else:
                ev.append(line)
    else:
        fg, bg = css_fallback_colors(p)
        ratio = contrast(fg, bg)
        ev.append("method: CSS parse fallback (Chrome measurement unavailable) of body/html/:root colors only")
        line = f"body text rgb{tuple(round(x) for x in fg[:3])} on rgb{tuple(round(x) for x in bg[:3])}: {ratio:.2f}:1"
        if ratio < 4.5:
            c.add(WARN, "CONTRAST_LOW", line + " (under 4.5)")
        else:
            ev.append(line)
    c.evidence = "\n".join(ev)
    return c


# --------------------------------------------------------------------------- check 6: size

def check_size(p, page_path):
    c = Check(6, "Size / load weight")
    base = os.path.dirname(page_path)
    total = os.path.getsize(page_path)
    rows = [f"{os.path.basename(page_path)}: {total:,} bytes"]
    refs = set()
    for _, tag, src in p.srcs:
        refs.add(src)
    for _, href in p.stylesheets:
        refs.add(href)
    for css in p.style_blocks:
        refs.update(re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css))
    external = 0
    for ref in sorted(refs):
        if ref.lower().startswith(("http://", "https://", "//")):
            external += 1
            continue
        if ref.lower().startswith("data:"):
            continue
        f = os.path.normpath(os.path.join(base, urllib.parse.unquote(urllib.parse.urlsplit(ref).path)))
        if os.path.isfile(f):
            n = os.path.getsize(f)
            total += n
            rows.append(f"{ref}: {n:,} bytes")
    rows.append(f"total local load weight: {total:,} bytes ({total / 1024:.1f} KB)")
    if external:
        rows.append(f"{external} external resource(s) not counted")
    if total > 1_000_000:
        c.add(WARN, "SIZE_HEAVY", f"page loads {total / 1024 / 1024:.2f} MB; a one-page site should be well under 1 MB")
    c.evidence = "\n".join(rows)
    return c


# --------------------------------------------------------------------------- live

def check_live(url, page_path):
    c = Check(7, "Live URL (--live)")
    try:
        req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        c.add(FAIL, "LIVE_STATUS", f"{url} -> HTTP {e.code}")
        c.evidence = ""
        return c
    except Exception as e:
        c.add(FAIL, "LIVE_STATUS", f"{url} -> no response: {type(e).__name__}: {e}")
        c.evidence = ""
        return c
    local = read_bytes(page_path)
    ev = [f"{url} -> HTTP {status}, {len(body):,} bytes, sha256 {hashlib.sha256(body).hexdigest()[:16]}",
          f"local -> {len(local):,} bytes, sha256 {hashlib.sha256(local).hexdigest()[:16]}"]
    if body == local:
        ev.append("live page is byte-for-byte the same as the local file")
    else:
        a, b = local.decode("utf-8", "replace").splitlines(), body.decode("utf-8", "replace").splitlines()
        first = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
        c.add(WARN, "LIVE_DIFFERS", f"live page differs from the local file (first difference at line {first + 1}). "
                                    "Push your latest version, or wait a minute for GitHub Pages to update.")
    c.evidence = "\n".join(ev)
    return c


# --------------------------------------------------------------------------- receipt

def write_receipt(checks, page_path, facts_path, live, out_dir, stamp, exit_code, content_note=None):
    page_bytes = read_bytes(page_path)
    L = []
    L.append(f"# RECEIPT — verify_page — {stamp}")
    L.append("")
    L.append(f"- **Page:** `{page_path}`")
    L.append(f"- **Page sha256:** `{hashlib.sha256(page_bytes).hexdigest()}`")
    L.append(f"- **Allow-list:** `{facts_path}`")
    if content_note:
        L.append(f"- **Plus content file:** `{content_note}`")
    if live:
        L.append(f"- **Live URL:** {live}")
    L.append(f"- **Ran:** {datetime.now().isoformat(timespec='seconds')} with `python3 {' '.join(sys.argv)}`")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append("| # | Check | Result | FAIL | WARN |")
    L.append("|---|-------|--------|------|------|")
    for c in checks:
        L.append(f"| {c.num} | {c.name} | **{c.result}** | {c.count(FAIL)} | {c.count(WARN)} |")
    L.append("")
    overall = "FAIL" if exit_code == 1 else "PASS (with warnings)" if any(c.count(WARN) for c in checks) else "PASS"
    L.append(f"**Overall: {overall}. Exit code: {exit_code}** "
             f"({'something must be fixed before you submit' if exit_code else 'no blocking problems found'})")
    L.append("")
    fails = [(c, code, msg) for c in checks for lvl, code, msg in c.items if lvl == FAIL]
    warns = [(c, code, msg) for c in checks for lvl, code, msg in c.items if lvl == WARN]
    L.append(f"## Failures ({len(fails)})")
    L.append("")
    L.extend([f"- [{code}] (check {c.num}) {msg}" for c, code, msg in fails] or ["None."])
    L.append("")
    L.append(f"## Warnings ({len(warns)}) — read these, decide yourself")
    L.append("")
    L.extend([f"- [{code}] (check {c.num}) {msg}" for c, code, msg in warns] or ["None."])
    L.append("")
    L.append("## Evidence per check")
    for c in checks:
        L.append("")
        L.append(f"### {c.num}. {c.name}: {c.result}")
        L.append("")
        L.append("```")
        L.append(getattr(c, "evidence", "") or "(no extra evidence)")
        L.append("```")
        for w, png in sorted(getattr(c, "shots", {}).items()):
            L.append(f"![{w}px]({os.path.basename(png)})")
    L.append("")
    L.append(f"## Exit code: {exit_code}")
    L.append("")
    path = os.path.join(out_dir, f"RECEIPT-{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


# --------------------------------------------------------------------------- main

def add_content(facts, text):
    """Merge a content.md into the allow-list (numbers, X-of-Y, dates, number-words, sentences)."""
    nums = facts.setdefault("numbers", {})
    for n in extract_numbers(text):
        nums.setdefault(n, []).append("--content")
    facts["of_pairs"] = sorted(set(facts.get("of_pairs", [])) | extract_pairs(text))
    facts["dates"] = sorted(set(facts.get("dates", [])) | extract_dates(text))
    facts["number_words"] = sorted(set(facts.get("number_words", [])) | extract_number_words(text))
    facts["source_text"] = facts.get("source_text", "") + "\n" + text


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def resolve_page(target):
    target = os.path.abspath(os.path.expanduser(target))
    if os.path.isdir(target):
        target = os.path.join(target, "index.html")
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description="Double-check a page an agent built. Writes a receipt.")
    ap.add_argument("page", help="path to index.html, or the folder that contains it")
    ap.add_argument("--live", help="the published URL, to confirm it loads and matches the local file")
    ap.add_argument("--facts", default=os.path.join(KIT, "facts.json"), help="allow-list (default: facts.json in the kit)")
    ap.add_argument("--content", help="your content.md (from main, the copy YOU wrote): its numbers and sentences are added to the allow-list")
    ap.add_argument("--out", default=os.path.join(KIT, "receipts"), help="where receipts and screenshots go")
    a = ap.parse_args(argv)

    page = resolve_page(a.page)
    if not os.path.isfile(page):
        print(f"ERROR: no page found at {page}", file=sys.stderr)
        return 2
    try:
        facts = json.loads(read_bytes(a.facts).decode("utf-8"))
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read allow-list {a.facts}: {e}", file=sys.stderr)
        return 2
    if not isinstance(facts, dict) or not isinstance(facts.get("numbers"), dict):
        print(f"ERROR: {a.facts} is not a valid allow-list (no 'numbers' map). Start from checks/facts.json.", file=sys.stderr)
        return 2
    content_note = None
    if a.content:
        try:
            ctext = read_bytes(os.path.expanduser(a.content)).decode("utf-8")
        except OSError as e:
            print(f"ERROR: cannot read --content {a.content}: {e}", file=sys.stderr)
            return 2
        add_content(facts, ctext)
        content_note = os.path.abspath(os.path.expanduser(a.content))
    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    p = PageParser()
    p.feed(read_bytes(page).decode("utf-8", "replace"))
    p.finish()

    checks = [check_facts(p, facts), check_links(p, page, facts), check_html(p)]
    render, measured = check_render(page, a.out, stamp)
    checks += [render, check_contrast(p, measured), check_size(p, page)]
    if a.live:
        checks.append(check_live(a.live, page))

    exit_code = 1 if any(c.result == FAIL for c in checks) else 0
    receipt = write_receipt(checks, page, os.path.abspath(a.facts), a.live, a.out, stamp, exit_code, content_note)
    for c in checks:
        print(f"{c.result:4}  {c.num}. {c.name}  ({c.count(FAIL)} fail, {c.count(WARN)} warn)")
    print(f"receipt: {receipt}")
    print(f"exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
