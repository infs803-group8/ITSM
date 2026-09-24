import Ajv2020, { type ErrorObject } from "ajv/dist/2020";
import addFormats from "ajv-formats";
import fixtures from "./fixtures.generated.json";

export type MockOperation = keyof typeof fixtures.operations;
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addFormat("int64", { type: "number", validate: Number.isSafeInteger });
ajv.addFormat("password", true);

const validators = new Map<string, ReturnType<typeof ajv.compile>>();
function validate(key: string, schema: object, value: unknown): ErrorObject[] | null {
  let validator = validators.get(key);
  if (!validator) {
    validator = ajv.compile({ ...schema, components: fixtures.components });
    validators.set(key, validator);
  }
  return validator(value) ? null : validator.errors ?? [];
}

export function validateBody(operation: MockOperation, value: unknown): ErrorObject[] | null {
  const schema = fixtures.operations[operation].requestSchema;
  return schema ? validate(`${operation}:body`, schema, value) : null;
}

export function validateQuery(operation: MockOperation, search: URLSearchParams): ErrorObject[] | null {
  for (const parameter of fixtures.operations[operation].parameters) {
    if (parameter.in !== "query" || !search.has(parameter.name)) continue;
    const raw = search.get(parameter.name)!;
    const schema = parameter.schema;
    const value = "type" in schema && schema.type === "integer"
      ? (raw.trim() === "" ? Number.NaN : Number(raw)) : raw;
    const errors = validate(`${operation}:query:${parameter.name}`, schema, value);
    if (errors) return errors;
  }
  return null;
}
