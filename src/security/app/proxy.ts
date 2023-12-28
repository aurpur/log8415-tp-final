import { logger } from "https://deno.land/x/hono@v3.11.4/middleware.ts";
import { Hono } from "https://deno.land/x/hono@v3.11.4/mod.ts";
import { Client } from "https://deno.land/x/mysql@v2.12.1/mod.ts";
// https://www.npmjs.com/package/sql-summary
import sqlSummary from "npm:sql-summary@^1.0.1";

// Load config file
const configPath = Deno.args[0] || "./config.json";
console.log(`Loading config from ${configPath}`);
const config = JSON.parse(await Deno.readTextFile(configPath));

async function createClients(
  managerHostname: string,
  workerHostnames: string[],
  username: string,
  password: string,
  db: string
) {
  const manager = await new Client().connect({
    hostname: managerHostname,
    username,
    password,
    db,
  });
  const workers = await Promise.all(
    workerHostnames.map((hostname) =>
      new Client().connect({
        hostname,
        username,
        password,
        db,
      })
    )
  );
  return { manager, workers };
}

// Create mysql clients
const clients = await createClients(
  config.manager,
  config.workers,
  config.username,
  config.password,
  config.db
);

/**
 * Execute query on the right instance(s)
 * @param query
 * @param worker Function that returns the selected worker in case of a read-only query
 * @returns Query result (always from the manager in case of a write query)
 */
async function execute(query: string, worker: () => Client | Promise<Client>) {
  const summary = sqlSummary(query) as string;
  if (summary.includes("SELECT") && !summary.includes("UPDATE")) {
    // Read-only query, can be executed on any instance
    const w = await worker();
    console.log(`Executing read query on ${w.config.hostname}: ${query}`);
    return await w.execute(query);
  } else {
    console.log(`Executing write query on all instances: ${query}`);
    // Write query, must be executed on all instances
    clients.workers.map((worker) => worker.execute(query));
    return await clients.manager.execute(query); // Return the result from the manager
  }
}

const app = new Hono();

app.use("*", logger());

/**
 * Direct hit: always execute the query on the manager
 */
app.post("/direct", async (c) => {
  const body = await c.req.json();
  const res = await execute(body.query, () => clients.manager);
  return c.json(res);
});

/**
 * Random: randomly select a worker
 */
app.post("/random", async (c) => {
  const body = await c.req.json();
  const res = await execute(body.query, () => {
    // Random selection
    const index = Math.floor(Math.random() * clients.workers.length);
    return clients.workers[index];
  });
  return c.json(res);
});

/**
 * Customized: select the worker with the lowest ping time
 */
app.post("/customized", async (c) => {
  const body = await c.req.json();
  const res = await execute(body.query, async () => {
    const allClients = [clients.manager, ...clients.workers];
    // Ping all instances with a SELECT 1 query
    const pingTimes = await Promise.all(
      allClients.map(
        (worker) =>
          new Promise<number>((resolve, reject) => {
            const start = Date.now();
            worker
              .query("SELECT 1")
              .then(() => {
                const end = Date.now();
                resolve(end - start);
              })
              .catch(reject);
          })
      )
    );
    console.log("ping times", pingTimes);
    // Select the worker with the lowest ping time
    const index = pingTimes.indexOf(Math.min(...pingTimes));
    return allClients[index];
  });
  return c.json(res);
});

Deno.serve({ port: 9000, hostname: "0.0.0.0" }, app.fetch);
