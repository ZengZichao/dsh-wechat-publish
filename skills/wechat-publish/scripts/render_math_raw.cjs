#!/usr/bin/env node
// Render LaTeX formulas to RAW MathJax SVG (like NeuraPress does).
//
// No transform baking, no flattening, no RDP simplification.
// Just MathJax's native SVG output with data-* attributes stripped.
//
// WeChat's draft API PRESERVES <g transform> (confirmed by read-back test),
// so the native MathJax coordinate system (viewBox + scale(1,-1) Y-flip +
// nested translate/scale for sub/superscripts) works correctly.
//
// Reads JSON from stdin:  [{ "tex": "...", "display": false }, ...]
// Writes JSON to stdout:  [ "<svg ...>...</svg>", ... ]

const mathjax = require("mathjax-full/js/mathjax.js").mathjax;
const TeX = require("mathjax-full/js/input/tex.js").TeX;
const SVG = require("mathjax-full/js/output/svg.js").SVG;
const liteAdaptor = require("mathjax-full/js/adaptors/liteAdaptor.js").liteAdaptor;
const RegisterHTMLHandler = require("mathjax-full/js/handlers/html.js").RegisterHTMLHandler;
const AllPackages = require("mathjax-full/js/input/tex/AllPackages.js").AllPackages;

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages });
const svg = new SVG({ fontCache: "none" });
const doc = mathjax.document("", { InputJax: tex, OutputJax: svg });

function cleanSvg(svgStr) {
  // Strip attributes that are not needed for rendering but add size:
  // data-mml-node, data-c, data-mjx-*, focusable, role
  let s = svgStr
    .replace(/\s+data-mml-node="[^"]*"/g, "")
    .replace(/\s+data-c="[^"]*"/g, "")
    .replace(/\s+data-mjx-[a-z]*="[^"]*"/g, "")
    .replace(/\s+focusable="[^"]*"/g, "")
    .replace(/\s+role="[^"]*"/g, "")
    .replace(/\s+xmlns="[^"]*"/g, ' xmlns="http://www.w3.org/2000/svg"');
  // Collapse multiple spaces
  s = s.replace(/  +/g, " ");
  return s;
}

let input;
try {
  input = JSON.parse(require("fs").readFileSync(0, "utf8"));
} catch (e) {
  process.stderr.write("bad input JSON: " + e.message + "\n");
  process.exit(1);
}

const out = input.map((item) => {
  const texStr = String(item.tex || "").trim();
  try {
    const node = doc.convert(texStr, { display: !!item.display });
    const svgNode = adaptor.childNodes(node)[0];
    if (!svgNode || adaptor.kind(svgNode) !== "svg") throw new Error("no svg");
    const raw = adaptor.outerHTML(svgNode);
    return cleanSvg(raw);
  } catch (e) {
    return '<span class="math-fallback">\\(' + texStr + "\\)</span>";
  }
});

process.stdout.write(JSON.stringify(out));
