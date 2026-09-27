import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createClient } from "@hey-api/openapi-ts";
import YAML from "yaml";
import { contractPath, frontendRoot, generatorConfig } from "../openapi.config.mjs";

const check = process.argv.includes("--check");
const stagingRoot = await mkdtemp(path.join(os.tmpdir(), "itsm-api-generation-"));
const generatedDirectory = "src/api/generated";
const fixturesFile = "src/mocks/fixtures.generated.json";
const workspaceFixturesFile = "src/mocks/workspace-fixtures.generated.json";
const mockOperations = new Set([
  "api01Health", "api08Register", "api09Login", "api10GetMyProfile",
  "api11UpdateMyProfile", "api12ReferenceData", "api15CreateTicket",
  "api16ListTickets", "api17GetTicket",
]);

async function filesIn(directory) {
  const entries = await readdir(directory, { withFileTypes: true }).catch((error) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  const files = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? filesIn(target) : [target];
  }));
  return files.flat();
}

async function readNormalized(file) {
  try {
    return (await readFile(file, "utf8")).replace(/\r\n/g, "\n");
  } catch (error) {
    if (error.code === "ENOENT") return undefined;
    throw error;
  }
}

try {
  const source = (await readFile(contractPath, "utf8")).replace(/\r\n/g, "\n");
  const contract = YAML.parse(source);
  const resolve = (value) => value?.$ref
    ? resolve(value.$ref.slice(2).split("/").reduce((node, key) => node[key], contract))
    : value;
  await createClient({ ...generatorConfig(stagingRoot), configFile: false });

  const fixtures = {};
  const workspaceFixtures = {};
  const schemas = {};
  function collectSchemas(value) {
    if (!value || typeof value !== "object") return;
    if (value.$ref?.startsWith("#/components/schemas/")) {
      const name = value.$ref.split("/").at(-1);
      if (!schemas[name]) {
        schemas[name] = resolve(value);
        collectSchemas(schemas[name]);
      }
    }
    for (const child of Object.values(value)) collectSchemas(child);
  }
  let operationCount = 0;
  for (const [url, pathItem] of Object.entries(contract.paths)) {
    for (const [method, operation] of Object.entries(pathItem)) {
      if (!operation.operationId) continue;
      operationCount += 1;
      const success = Object.entries(operation.responses).find(([status]) => /^2\d\d$/.test(status));
      const media = success?.[1].content?.["application/json"];
      const body = media?.example ?? resolve(Object.values(media?.examples ?? {})[0])?.value;
      if (body === undefined) throw new Error(`Missing success example: ${operation.operationId}`);
      const requestSchema = resolve(operation.requestBody)?.content?.["application/json"]?.schema ?? null;
      const parameters = [...(pathItem.parameters ?? []), ...(operation.parameters ?? [])].map(resolve);
      const fixture = { method, path: url, status: Number(success[0]), body, requestSchema, parameters };
      workspaceFixtures[operation.operationId] = fixture;
      if (mockOperations.has(operation.operationId)) {
        collectSchemas(requestSchema);
        collectSchemas(parameters);
        fixtures[operation.operationId] = fixture;
      }
    }
  }
  if (Object.keys(fixtures).length !== mockOperations.size) throw new Error("A baseline Mock operation is missing from the contract.");
  const manifest = {
    source: "docs/api/openapi.yaml",
    version: contract.info.version,
    sha256: createHash("sha256").update(source).digest("hex"),
    operations: operationCount,
  };
  await writeFile(path.join(stagingRoot, generatedDirectory, "contract-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await mkdir(path.dirname(path.join(stagingRoot, fixturesFile)), { recursive: true });
  await writeFile(path.join(stagingRoot, fixturesFile), `${JSON.stringify({ operations: fixtures, components: { schemas } }, null, 2)}\n`);
  await writeFile(path.join(stagingRoot, workspaceFixturesFile), `${JSON.stringify({ operations: workspaceFixtures, components: contract.components }, null, 2)}\n`);

  const expected = (await filesIn(path.join(stagingRoot, generatedDirectory))).map((file) => path.relative(stagingRoot, file));
  expected.push(fixturesFile);
  expected.push(workspaceFixturesFile);
  const current = (await filesIn(path.join(frontendRoot, generatedDirectory))).map((file) => path.relative(frontendRoot, file));
  const changed = [];
  for (const file of new Set([...expected, ...current])) {
    const wanted = await readNormalized(path.join(stagingRoot, file));
    const existing = await readNormalized(path.join(frontendRoot, file));
    if (wanted === existing) continue;
    changed.push(file);
    if (!check) {
      const target = path.join(frontendRoot, file);
      if (wanted === undefined) {
        // Only remove an individual stale generated file discovered above.
        await rm(target);
      } else {
        await mkdir(path.dirname(target), { recursive: true });
        await writeFile(target, wanted);
      }
    }
  }
  if (check && changed.length) {
    console.error(`Generated API files are out of date:\n${changed.join("\n")}\nRun npm run api:generate.`);
    process.exitCode = 1;
  } else {
    console.log(`${check ? "Verified" : "Generated"} ${operationCount} API operations, ${mockOperations.size} baseline and ${Object.keys(workspaceFixtures).length} workspace Mock fixtures.`);
  }
} finally {
  // mkdtemp returned this exact task-owned directory; no project directory is removed.
  await rm(stagingRoot, { recursive: true, force: true });
}
