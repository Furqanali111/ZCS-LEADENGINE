US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
CRM_STATUSES = ("new", "in_progress", "researching", "email_sent", "called", "follow_up_required", "interested", "meeting_scheduled", "not_interested", "converted", "do_not_contact")
JOB_STATUSES = ("queued", "running", "paused", "completed", "cancelled", "failed")
ORG_TYPES = ("practice", "subpart", "hospital", "solo_provider")
PRIORITIES = ("critical", "high", "medium", "low")
CLOSED_STATUSES = ("converted", "not_interested", "do_not_contact")
ACTIVITY_TYPES = ("call", "email", "meeting", "note", "status_change", "outcome")
OUTCOMES = ("no_answer", "spoke", "interested", "not_interested", "meeting_booked", "converted", "other")
SUPPRESSION_KINDS = ("npi", "phone", "email")
ENRICHMENT_STATUSES = ("not_run", "enriched", "no_website_found", "failed", "rejected_by_user")
TEMPLATE_KINDS = ("email", "call")
