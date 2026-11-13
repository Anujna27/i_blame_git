from core.erasure_journal import ErasureJournal


def test_journal_tracks_completion_and_pending_operations(tmp_path):
    journal = ErasureJournal(str(tmp_path / "journal.json"))
    pending_id = journal.begin("pending-entity", "privacy-service", "user request")
    journal.advance(pending_id, "mutating")
    assert len(journal.pending()) == 1

    done_id = journal.begin("done-entity", "privacy-service", "user request")
    journal.complete(done_id, "fully_deleted")
    assert [entry["entity_id"] for entry in journal.pending()] == ["pending-entity"]

    reloaded = ErasureJournal(str(tmp_path / "journal.json"))
    assert reloaded.pending()[0]["operation_id"] == pending_id
