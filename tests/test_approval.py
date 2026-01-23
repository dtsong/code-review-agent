"""Tests for approval workflow."""

from unittest.mock import MagicMock, patch

from pr_review_agent.escalation.approval import ApprovalDecision, ApprovalManager


class TestApprovalDecision:
    def test_dataclass_fields(self):
        decision = ApprovalDecision(
            review_event_id="uuid-123",
            decision="approved",
            decided_by="reviewer@example.com",
            reason="Looks good after manual check",
            repo_owner="org",
            repo_name="repo",
            pr_number=42,
            pr_url="https://github.com/org/repo/pull/42",
        )
        assert decision.decision == "approved"
        assert decision.decided_by == "reviewer@example.com"

    def test_optional_fields_default(self):
        decision = ApprovalDecision(
            review_event_id="uuid-123",
            decision="dismissed",
            decided_by="admin",
        )
        assert decision.reason is None
        assert decision.repo_owner == ""
        assert decision.pr_number == 0


class TestApprovalManager:
    @patch("pr_review_agent.escalation.approval.create_client")
    def test_record_decision_success(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        # Mock insert chain
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{"id": "decision-uuid-1"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = (
            mock_insert_result
        )

        # Mock update chain
        mock_update_result = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_update_result
        )

        manager = ApprovalManager("https://supabase.example", "key")
        decision = ApprovalDecision(
            review_event_id="review-uuid-1",
            decision="approved",
            decided_by="admin@org.com",
            reason="Verified manually",
            repo_owner="org",
            repo_name="repo",
            pr_number=10,
            pr_url="https://github.com/org/repo/pull/10",
        )

        result = manager.record_decision(decision)
        assert result == "decision-uuid-1"

        # Verify insert was called with correct data
        insert_call = mock_client.table.return_value.insert.call_args
        data = insert_call[0][0]
        assert data["review_event_id"] == "review-uuid-1"
        assert data["decision"] == "approved"
        assert data["decided_by"] == "admin@org.com"

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_record_decision_updates_outcome(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        mock_insert_result = MagicMock()
        mock_insert_result.data = [{"id": "id"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = (
            mock_insert_result
        )

        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        manager = ApprovalManager("url", "key")
        decision = ApprovalDecision(
            review_event_id="rev-1",
            decision="overridden",
            decided_by="user",
        )
        manager.record_decision(decision)

        # Verify update was called
        mock_client.table.return_value.update.assert_called()

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_record_decision_handles_exception(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.side_effect = (
            Exception("DB error")
        )

        manager = ApprovalManager("url", "key")
        decision = ApprovalDecision(
            review_event_id="rev-1",
            decision="approved",
            decided_by="user",
        )
        result = manager.record_decision(decision)
        assert result is None

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_get_pending_reviews(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"id": "1", "pr_number": 10, "confidence_score": 0.3},
            {"id": "2", "pr_number": 11, "confidence_score": 0.2},
        ]
        (
            mock_client.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ) = mock_result

        manager = ApprovalManager("url", "key")
        reviews = manager.get_pending_reviews()
        assert len(reviews) == 2

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_get_pending_reviews_with_filters(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [{"id": "1"}]
        (
            mock_client.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = mock_result

        manager = ApprovalManager("url", "key")
        reviews = manager.get_pending_reviews(
            repo_owner="org", repo_name="repo"
        )
        assert len(reviews) == 1

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_get_pending_reviews_handles_exception(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        (
            mock_client.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
            .execute.side_effect
        ) = Exception("DB error")

        manager = ApprovalManager("url", "key")
        reviews = manager.get_pending_reviews()
        assert reviews == []

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_get_audit_trail(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"id": "d1", "decision": "approved", "decided_by": "admin"},
            {"id": "d2", "decision": "dismissed", "decided_by": "reviewer"},
        ]
        (
            mock_client.table.return_value
            .select.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ) = mock_result

        manager = ApprovalManager("url", "key")
        trail = manager.get_audit_trail()
        assert len(trail) == 2
        assert trail[0]["decision"] == "approved"

    @patch("pr_review_agent.escalation.approval.create_client")
    def test_get_audit_trail_handles_exception(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        (
            mock_client.table.return_value
            .select.return_value
            .order.return_value
            .limit.return_value
            .execute.side_effect
        ) = Exception("DB error")

        manager = ApprovalManager("url", "key")
        trail = manager.get_audit_trail()
        assert trail == []
