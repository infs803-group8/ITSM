// Compatibility export; the API contract is the only DTO source.
import type { Api08RegisterData, Api09LoginData } from "./generated/types.gen";

export type * from "./generated/types.gen";
export type { ErrorResponse as ApiError } from "./generated/types.gen";

// Default read/write splitting keeps password in the operation's writable body.
// Derive input aliases from the SDK rather than duplicating fields by hand.
export type RegisterRequest = Api08RegisterData["body"];
export type LoginRequest = Api09LoginData["body"];
