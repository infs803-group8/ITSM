from app.main import app


def test_api_08_to_11_routes_are_registered_with_frozen_operation_ids():
    operations = {
        (method.upper(), path): operation.get("operationId")
        for path, path_item in app.openapi()["paths"].items()
        for method, operation in path_item.items()
        if method.lower() in {"get", "post", "patch"}
    }

    assert operations[("POST", "/api/v1/auth/register")] == "api08Register"
    assert operations[("POST", "/api/v1/auth/login")] == "api09Login"
    assert operations[("GET", "/api/v1/users/me")] == "api10GetMyProfile"
    assert operations[("PATCH", "/api/v1/users/me")] == "api11UpdateMyProfile"


def test_auth_request_models_reject_additional_fields_in_openapi():
    schemas = app.openapi()["components"]["schemas"]
    assert schemas["RegisterRequest"]["additionalProperties"] is False
    assert schemas["LoginRequest"]["additionalProperties"] is False
    assert schemas["UpdateProfileRequest"]["additionalProperties"] is False
