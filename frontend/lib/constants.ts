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
];

export const CRM_STATUSES: { value: string; label: string }[] = [
  { value: "new", label: "New" },
  { value: "researching", label: "Researching" },
  { value: "email_sent", label: "Email sent" },
  { value: "called", label: "Called" },
  { value: "follow_up_required", label: "Follow-up required" },
  { value: "interested", label: "Interested" },
  { value: "meeting_scheduled", label: "Meeting scheduled" },
  { value: "not_interested", label: "Not interested" },
  { value: "converted", label: "Converted" },
  { value: "do_not_contact", label: "Do not contact" },
];

export const PRIORITIES: { value: string; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
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
