import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, restoreVietnameseInHtml } from "../src/components/ui/MathRenderer.js";

test("escapeHtml sanitizes all dangerous HTML characters", () => {
  const unsafe = `<script>alert("xss & 'pwn'")</script>`;
  const safe = escapeHtml(unsafe);
  assert.equal(safe, "&lt;script&gt;alert(&quot;xss &amp; &#39;pwn&#39;&quot;)&lt;/script&gt;");
  assert.ok(!safe.includes("<"));
  assert.ok(!safe.includes(">"));
});

test("restoreVietnameseInHtml escapes payload in text tokens to prevent XSS", () => {
  const template = `<span class="katex-html">VNTEXT0END</span>`;
  const restores = [{ token: "VNTEXT0END", text: `<img src=x onerror=alert('hacked')> Tiếng Việt` }];
  const result = restoreVietnameseInHtml(template, restores);
  
  assert.doesNotMatch(result, /<img/);
  assert.match(result, /&lt;img src=x onerror=alert\(&#39;hacked&#39;\)&gt;/);
  assert.match(result, /Tiếng Việt/);
});
