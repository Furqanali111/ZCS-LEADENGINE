export const US_STATES: { code: string; name: string }[] = [
  ["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"], ["AR", "Arkansas"],
  ["CA", "California"], ["CO", "Colorado"], ["CT", "Connecticut"], ["DE", "Delaware"],
  ["DC", "District of Columbia"], ["FL", "Florida"], ["GA", "Georgia"], ["HI", "Hawaii"],
  ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"], ["IA", "Iowa"],
  ["KS", "Kansas"], ["KY", "Kentucky"], ["LA", "Louisiana"], ["ME", "Maine"],
  ["MD", "Maryland"], ["MA", "Massachusetts"], ["MI", "Michigan"], ["MN", "Minnesota"],
  ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"], ["NE", "Nebraska"],
  ["NV", "Nevada"], ["NH", "New Hampshire"], ["NJ", "New Jersey"], ["NM", "New Mexico"],
  ["NY", "New York"], ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"],
  ["OK", "Oklahoma"], ["OR", "Oregon"], ["PA", "Pennsylvania"], ["RI", "Rhode Island"],
  ["SC", "South Carolina"], ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"],
  ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"], ["WA", "Washington"],
  ["WV", "West Virginia"], ["WI", "Wisconsin"], ["WY", "Wyoming"],
].map(([code, name]) => ({ code, name }));

export const SPECIALTIES = [
  "Internal Medicine",
  "Family Medicine",
  "Geriatric Medicine",
  "General Practice",
  "Nurse Practitioner",
  "Pediatrics",
  "Cardiology",
  "Endocrinology",
  "Nephrology",
  "Pulmonary Disease",
  "Psychiatry & Neurology",
  "Orthopaedic Surgery",
  "Obstetrics & Gynecology",
];

// Stored values belong to the backend; labels and hints are display only.
export const CRM_STATUSES: { value: string; label: string; hint: string }[] = [
  { value: "new", label: "New", hint: "Found by a search, nobody has touched it yet" },
  { value: "in_progress", label: "Being worked", hint: "Claimed by a salesperson, being worked" },
  { value: "researching", label: "Researching", hint: "Looking up the practice before the first contact" },
  { value: "email_sent", label: "Email sent", hint: "First email sent, waiting for a reply" },
  { value: "called", label: "Called", hint: "Called at least once, no decision yet" },
  { value: "called_no_answer", label: "Called, no answer", hint: "Called but nobody picked up, try again" },
  { value: "follow_up_required", label: "Follow-up due", hint: "Contacted, a next step is due" },
  { value: "interested", label: "Interested", hint: "The practice wants to hear more" },
  { value: "meeting_scheduled", label: "Meeting booked", hint: "A call or meeting is on the calendar" },
  { value: "not_interested", label: "Not interested", hint: "The practice said no, closed" },
  { value: "converted", label: "Converted", hint: "The practice became a client, closed" },
  { value: "do_not_contact", label: "Do not contact", hint: "Opted out, never contact again, closed" },
];

export const ACTIVITY_TYPES: { value: string; label: string }[] = [
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "note", label: "Note" },
  { value: "status_change", label: "Status change" },
  { value: "outcome", label: "Outcome" },
];

export const OUTCOMES: { value: string; label: string }[] = [
  { value: "no_answer", label: "No answer" },
  { value: "spoke", label: "Spoke" },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not interested" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "converted", label: "Converted" },
  { value: "other", label: "Other" },
];

export const SUPPRESSION_KINDS: { value: string; label: string }[] = [
  { value: "npi", label: "NPI" },
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
];

// Closed leads never count as follow-ups due.
export const CLOSED_STATUSES: { value: string; label: string }[] = [
  { value: "converted", label: "Converted" },
  { value: "not_interested", label: "Not interested" },
  { value: "do_not_contact", label: "Do not contact" },
];

export const PRIORITIES: { value: string; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export const ORG_TYPES: { value: string; label: string }[] = [
  { value: "practice", label: "Practice" },
  { value: "solo_provider", label: "Solo provider" },
  { value: "subpart", label: "Hospital or system subpart" },
  { value: "hospital", label: "Hospital" },
];

export const SCORE_FACTORS: { key: string; label: string }[] = [
  { key: "specialty", label: "Specialty" },
  { key: "independence", label: "Independence" },
  { key: "service_fit", label: "Service fit" },
  { key: "contactability", label: "Contactability" },
  { key: "decision_maker", label: "Decision-maker" },
  { key: "multi_location", label: "Multiple locations" },
];

export const SOURCE_STATUS_LABELS: Record<string, string> = {
  approved_not_built: "Approved, not built yet",
  not_reviewed: "Not reviewed yet",
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  cancelled: "Cancelled",
  failed: "Failed",
};
