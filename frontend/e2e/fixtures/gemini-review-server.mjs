// SSR fixture only: no credentials, model calls or database access.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("./gemini-review.json", import.meta.url), "utf8"));
createServer((request, response) => {
  const path = new URL(request.url, "http://127.0.0.1:8897").pathname;
  const body = path.endsWith("/problem") ? fixture.problem
    : path.endsWith("/ink") ? fixture.document
    : path.endsWith("/ink/pages/0") ? fixture.page
    : fixture.attempt;
  response.writeHead(200, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}).listen(8897, "127.0.0.1");
