"""Provision only the reviewed GitHub OIDC provider and project release role.

Run in AWS CloudShell from the repository root after reviewing the two JSON policies.
Without --apply this only prints the proposed account, role and permissions.
"""

import argparse
import json
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "256329410824"
ROLE = "infs803-group8-itsm-github-release"
PROVIDER = f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    trust = json.loads((ROOT / "policies/github-actions-trust.json").read_text())
    policy = json.loads((ROOT / "policies/github-actions-release.json").read_text())
    print(
        json.dumps(
            {"account": ACCOUNT, "role": ROLE, "trust": trust, "permissions": policy}, indent=2
        )
    )
    if not args.apply:
        return
    session = boto3.Session(region_name="ap-southeast-2")
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise RuntimeError("Unexpected account; no changes made")
    iam = session.client("iam")
    try:
        provider = iam.get_open_id_connect_provider(OpenIDConnectProviderArn=PROVIDER)
        if "sts.amazonaws.com" not in provider["ClientIDList"]:
            raise RuntimeError("Existing provider has a different audience; review required")
    except iam.exceptions.NoSuchEntityException:
        iam.create_open_id_connect_provider(
            Url="https://token.actions.githubusercontent.com",
            ClientIDList=["sts.amazonaws.com"],
            Tags=[{"Key": "Project", "Value": "infs803-group8-itsm"}],
        )
    try:
        role = iam.get_role(RoleName=ROLE)["Role"]
        if role["AssumeRolePolicyDocument"] != trust:
            raise RuntimeError("Existing role trust differs; refusing to overwrite it")
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=ROLE,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Manual GitHub Actions releases for infs803-group8/ITSM main only",
            MaxSessionDuration=3600,
            Tags=[{"Key": "Project", "Value": "infs803-group8-itsm"}],
        )["Role"]
    iam.put_role_policy(
        RoleName=ROLE, PolicyName="ManualEcsRelease", PolicyDocument=json.dumps(policy)
    )
    assert (
        iam.get_role_policy(RoleName=ROLE, PolicyName="ManualEcsRelease")["PolicyDocument"]
        == policy
    )
    print(f"AWS_RELEASE_ROLE_ARN={role['Arn']}")


if __name__ == "__main__":
    main()
