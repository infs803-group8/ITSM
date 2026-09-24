from app.domains.audit.model import TicketEvent


def test_ticket_event_mapper_resolves_without_other_domain_models():
    """Regression: ORM flush must not require unfinished Member B models."""
    assert list(TicketEvent.__mapper__._sorted_tables) == [TicketEvent.__table__]


def test_ticket_event_has_no_cross_domain_foreign_keys_mapped():
    """Cross-domain FKs stay enforced only in schema.sql, per model.py's
    docstring -- the ORM mapper must not declare any of them itself.
    """
    assert TicketEvent.__table__.foreign_keys == set()


def test_metadata_column_is_aliased_away_from_the_reserved_attribute():
    assert "metadata" in TicketEvent.__table__.columns
    assert not hasattr(TicketEvent, "metadata_json") or (
        TicketEvent.metadata_json.property.columns[0].name == "metadata"
    )
