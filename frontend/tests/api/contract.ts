import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import YAML from "yaml";

// Tests read the original team contract, not the generated Mock schema snapshot.
export const contract = YAML.parse(readFileSync(fileURLToPath(new URL("../../../docs/api/openapi.yaml", import.meta.url)), "utf8"));
export const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addFormat("int64", { type: "number", validate: Number.isSafeInteger });
ajv.addFormat("password", true);

// YAML parser output is untyped; application code uses generated DTOs instead.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function resolve(value: any): any {
  return value?.$ref ? resolve(value.$ref.slice(2).split("/").reduce((node: typeof contract, key: string) => node[key], contract)) : value;
}

export const operations = Object.entries(contract.paths).flatMap(([path, pathItem]) =>
  Object.entries(pathItem as Record<string, typeof contract>).filter(([, operation]) => operation.operationId)
    .map(([method, operation]) => ({ path, method, ...operation })),
);

export function responseSchema(operationId: string, status = 200) {
  const operation = operations.find((item) => item.operationId === operationId);
  if (!operation) throw new Error(`Unknown operation: ${operationId}`);
  const response = resolve(operation.responses[status]);
  if (!response) throw new Error(`Status ${status} not specified for ${operationId}`);
  return { ...response.content["application/json"].schema, components: contract.components };
}

export function successExample(operationId: string) {
  const operation = operations.find((item) => item.operationId === operationId);
  const status = Object.keys(operation.responses).find((code) => /^2\d\d$/.test(code))!;
  const media = resolve(operation.responses[status]).content["application/json"];
  return structuredClone(media.example ?? resolve(Object.values(media.examples)[0]).value);
}

export function assertResponse(operationId: string, status: number, body: unknown): void {
  const validator = ajv.compile(responseSchema(operationId, status));
  if (!validator(body)) throw new Error(`${operationId}/${status}: ${ajv.errorsText(validator.errors)}`);
}
