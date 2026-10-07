"""vendor_workflow request/response schemas (C029/C030).

``TicketActionResponse``/``TicketActionData``/``AvailableAction`` and the
``VendorRequestView``/``VendorResponseView``/``VendorOrganisationView``
payload shapes all already live in ``app.domains.workflow.schema`` (built
for the shared write-path response contract every C024-C034 action
returns) -- this module only adds the two request bodies unique to this
domain's own endpoints, copied field-for-field from openapi.yaml.
"""

from pydantic import BaseModel, Field


class VendorRequestCreate(BaseModel):
    """backend/contracts/openapi.yaml: VendorRequestCreate (API-26)."""

    vendor_org_id: int
    vendor_message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class VendorResponseRequest(BaseModel):
    """backend/contracts/openapi.yaml: VendorResponseRequest (API-27)."""

    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}
