import { fileURLToPath } from "node:url";
import path from "node:path";

export const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
export const contractPath = path.resolve(frontendRoot, "../docs/api/openapi.yaml");

// The staging root has the same layout, so generated imports are reproducible.
export function generatorConfig(outputRoot = frontendRoot) {
  return {
    input: contractPath,
    // v1.1 marks LoginData.access_token both required in responses and writeOnly.
    // Preserve declared fields until the contract owner resolves that annotation.
    parser: { transforms: { readWrite: false } },
    output: {
      path: path.join(outputRoot, "src/api/generated"),
    },
    plugins: [
      "@hey-api/typescript",
      {
        name: "@hey-api/client-axios",
        baseUrl: false,
        throwOnError: true,
        runtimeConfigPath: path.join(outputRoot, "src/api/httpClient"),
      },
      "@hey-api/sdk",
    ],
  };
}

export default generatorConfig();
