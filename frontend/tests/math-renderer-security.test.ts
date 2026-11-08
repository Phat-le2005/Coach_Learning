import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, formatPlainText, restoreVietnameseInHtml } from "../src/components/ui/MathRenderer.js";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MathRenderer } from "../src/components/ui/MathRenderer.js";

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

test("curated grouped-data table keeps intervals, frequencies and surrounding paragraphs", () => {
  const text = "Mẫu số liệu\n\n| Khoảng lớp | Tần số |\n|---|---:|\n| [200; 250) | 24 |\n| [250; 300) | 62 |\n\nTính các tứ phân vị.";
  const result = formatPlainText(text);
  assert.match(result, /Mẫu số liệu<br\/><br\/><div/);
  assert.match(result, /<th scope="col"[^>]*>Khoảng lớp<\/th>/);
  assert.match(result, /<td[^>]*>\[200; 250\)<\/td><td[^>]*>24<\/td>/);
  assert.match(result, /<\/div><br\/><br\/>Tính các tứ phân vị\./);
  assert.equal((result.match(/<tr>/g) ?? []).length, 3);
});

test("probability table treats source HTML and escaped pipes as cell text", () => {
  const result = formatPlainText("Màu | Có đánh số | Không đánh số\n--- | --- | ---\nĐỏ | 20 | 20\nVàng | 36 | <img src=x onerror=alert('x')> \\| 24");
  assert.match(result, /<thead>/);
  assert.match(result, /&lt;img src=x onerror=alert\(&#39;x&#39;\)&gt; \| 24/);
  assert.doesNotMatch(result, /<img/);
  assert.equal((result.match(/<td /g) ?? []).length, 6);
});

test("plain paragraphs and non-table pipes keep the existing text flow", () => {
  assert.equal(formatPlainText("Dòng một\nDòng tiếp.\n\nĐoạn hai."), "Dòng một Dòng tiếp.<br/><br/>Đoạn hai.");
  assert.equal(formatPlainText("A | B\nchưa có separator"), "A | B chưa có separator");
  assert.doesNotMatch(formatPlainText("| A | B |\n|---|---|"), /<table/);
});

test("actual MathRenderer renders a data table alongside existing inline formulas", () => {
  const content = "Cho mẫu số liệu:\n\n| Khoảng | Tần số |\n|---|---|\n| [0; 5) | 10 |\n\nTính $Q_1$ và $Q_3$.";
  const result = renderToStaticMarkup(React.createElement(MathRenderer, { content }));
  assert.match(result, /<table /);
  assert.match(result, /<th scope="col"/);
  assert.match(result, /class="katex"/);
  assert.match(result, /Q/);
  assert.doesNotMatch(result, /\|---\|/);
});
