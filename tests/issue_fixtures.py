"""Seed authoritative fake external Issues; never create local-only tasks."""
import uuid


def seed_issue(store, prompt):
    return store.import_issue(provider='fixture', instance='fixture/repo',
                              external_id=uuid.uuid4().hex, prompt=prompt)
