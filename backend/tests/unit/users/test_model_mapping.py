from app.domains.users.model import User, UserSkill, VendorOrganisation


def test_user_model_matches_canonical_column_names():
    assert set(User.__table__.columns.keys()) == {
        "user_id",
        "email",
        "password_hash",
        "display_name",
        "role_code",
        "is_available",
        "vendor_org_id",
        "is_active",
        "last_assigned_at",
        "created_at",
        "updated_at",
    }
    assert set(UserSkill.__table__.columns.keys()) == {
        "user_id",
        "category_code",
        "created_at",
    }
    assert set(VendorOrganisation.__table__.columns.keys()) == {
        "vendor_org_id",
        "name",
        "is_active",
        "created_at",
        "updated_at",
    }
