import { logger } from "https://deno.land/x/hono@v3.11.4/middleware.ts";
import { Hono } from "https://deno.land/x/hono@v3.11.4/mod.ts";

// Load config file
const configPath = Deno.args[0] || "./config.json";
console.log(`Loading config from ${configPath}`);
const config = JSON.parse(await Deno.readTextFile(configPath));

const app = new Hono();

app.use("*", logger());

app.post("/:implem", async (c) => {
  const implem = c.req.param("implem");

  // Sanitization
  const body = await c.req.json();
  const query = body.query.replace(/['";]/g, ""); // Basic regex sanitization

  // Forward request to proxy
  const resp = await fetch(`${config.proxy}/${implem}`, {
    method: "POST",
    body: JSON.stringify({ query }),
  });

  // Return response from proxy
  c.status(resp.status);
  if (resp.ok) {
    return c.json(await resp.json());
  } else {
    return c.text(await resp.text());
  }
});

Deno.serve({ port: 8000, hostname: "0.0.0.0" }, app.fetch);
