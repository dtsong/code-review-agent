"""Approval workflow for escalated reviews."""

from dataclasses import dataclass

from supabase import Client, create_client


@dataclass
class ApprovalDecision:
    """Record of a human approval decision."""

    review_event_id: str
    decision: str  # approved, overridden, dismissed
    decided_by: str
    reason: str | None = None
    repo_owner: str = ""
    repo_name: str = ""
    pr_number: int = 0
    pr_url: str = ""


class ApprovalManager:
    """Manages approval decisions in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize with Supabase credentials."""
        self.client: Client = create_client(supabase_url, supabase_key)

    def record_decision(self, decision: ApprovalDecision) -> str | None:
        """Record an approval decision. Returns the decision ID."""
        data = {
            "review_event_id": decision.review_event_id,
            "decision": decision.decision,
            "decided_by": decision.decided_by,
            "reason": decision.reason,
            "repo_owner": decision.repo_owner,
            "repo_name": decision.repo_name,
            "pr_number": decision.pr_number,
            "pr_url": decision.pr_url,
        }

        try:
            result = (
                self.client.table("approval_decisions")
                .insert(data)
                .execute()
            )

            # Update the review_events outcome
            outcome = decision.decision
            self.client.table("review_events").update(
                {"outcome": outcome}
            ).eq("id", decision.review_event_id).execute()

            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def get_pending_reviews(
        self,
        repo_owner: str | None = None,
        repo_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get escalated reviews that haven't been actioned yet."""
        query = (
            self.client.table("review_events")
            .select("*")
            .eq("escalated_to_human", True)
            .eq("outcome", "escalated")
            .order("created_at", desc=True)
            .limit(limit)
        )

        if repo_owner:
            query = query.eq("repo_owner", repo_owner)
        if repo_name:
            query = query.eq("repo_name", repo_name)

        try:
            result = query.execute()
            return result.data if result.data else []
        except Exception:
            return []

    def get_audit_trail(
        self,
        repo_owner: str | None = None,
        repo_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get audit trail of approval decisions."""
        query = (
            self.client.table("approval_decisions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        if repo_owner:
            query = query.eq("repo_owner", repo_owner)
        if repo_name:
            query = query.eq("repo_name", repo_name)

        try:
            result = query.execute()
            return result.data if result.data else []
        except Exception:
            return []
